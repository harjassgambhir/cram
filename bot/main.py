"""
bot/main.py — CRAM-1 Telegram bot.

Doctors send a clinical scenario. The bot shows a research plan with inline
buttons (tap to skip branches, confirm, cancel). Research runs in background
(~15 min) and sends PDF + summary on completion. Follow-up questions answered
from session evidence.

No slash commands needed — everything is buttons.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent / ".env", override=True)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

from bot.intent import classify, casual_reply
from bot.session_map import (
    init_db, get_state, get_session_dir, get_scenario, set_idle,
    get_queued_scenario, set_queued_scenario, set_user_settings,
)
from bot.runner import start_research, run_chat_query, PlanSession, format_plan_message
from bot.formatter import (
    extract_summary,
    find_pdf_for_session,
    find_report_md_for_session,
    split_chunks,
    escape_md,
)
from bot.settings import (
    build_settings_message,
    build_settings_keyboard,
    build_model_keyboard,
    build_depth_keyboard,
    detect_model_preset,
    MODEL_PRESETS,
    get_run_params,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("cram-bot")

_plan_sessions: dict[str, PlanSession] = {}
_user_locks:    dict[str, asyncio.Lock] = {}

# Pending scenarios for queue prompt (uid → scenario text)
_pending_scenarios: dict[str, str] = {}

# Settings input state machine (uid → state string)
# States: "awaiting_key" | "awaiting_big_model" | "awaiting_small_model"
_settings_state: dict[str, str] = {}
_settings_pending: dict[str, dict] = {}  # uid → partial settings being built

# Run ID counter — incremented each time a research run starts for a user.
# _done_callback checks its run_id still matches before updating state,
# so stale threads from cancelled runs don't overwrite a new run's state.
_run_ids: dict[str, int] = {}  # uid → current run id


# ── Keyboard builders ──────────────────────────────────────────────────────────

def _kb_plan(branches: list) -> InlineKeyboardMarkup:
    """Inline keyboard for plan confirmation."""
    rows = []
    # Skip buttons — 3 per row
    skip_row = []
    for b in branches:
        bid = b.get("branch_id", "?")
        skip_row.append(InlineKeyboardButton(f"Skip [{bid}]", callback_data=f"plan:skip:{bid}"))
        if len(skip_row) == 3:
            rows.append(skip_row)
            skip_row = []
    if skip_row:
        rows.append(skip_row)
    # Confirm / cancel
    rows.append([
        InlineKeyboardButton("✅ Start Research", callback_data="plan:go"),
        InlineKeyboardButton("🚫 Cancel",         callback_data="plan:cancel"),
    ])
    return InlineKeyboardMarkup(rows)


def _kb_queue(scenario: str) -> InlineKeyboardMarkup:
    """Keyboard for when a new scenario arrives while one is running."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📥 Queue it",       callback_data="queue:add"),
        InlineKeyboardButton("⏹ Cancel current", callback_data="queue:cancel_current"),
        InlineKeyboardButton("✖ Dismiss",         callback_data="queue:dismiss"),
    ]])


def _kb_idle() -> InlineKeyboardMarkup:
    """Persistent keyboard after chat session."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔬 New research", callback_data="action:new"),
            InlineKeyboardButton("📚 History",      callback_data="action:history"),
        ],
        [InlineKeyboardButton("⚙️ Settings",        callback_data="settings:open")],
    ])


def _kb_cancel() -> InlineKeyboardMarkup:
    """Cancel button while researching."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏹ Cancel research", callback_data="action:cancel"),
    ]])


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _send(update: Update, text: str, reply_markup=None, parse_mode=None) -> None:
    for chunk in split_chunks(text, max_len=4000):
        await update.message.reply_text(chunk, reply_markup=reply_markup, parse_mode=parse_mode)
        reply_markup = None  # only attach markup to first chunk


async def _edit_or_send(query, text: str, reply_markup=None) -> None:
    """Edit the callback message if possible, otherwise send new."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception:
            await query.message.reply_text(text, reply_markup=reply_markup)


# ── Ready message with settings summary ───────────────────────────────────────

def _ready_message(uid: str) -> str:
    from bot.settings import get_run_params, detect_model_preset, DEPTH_PRESETS
    from bot.session_map import get_user_settings
    s   = get_user_settings(uid)
    p   = get_run_params(uid)
    preset = detect_model_preset(s["model_big"], s["model_small"])
    depth  = s["report_depth"] or "standard"
    n_branches, _ = DEPTH_PRESETS.get(depth, (6, 3))
    depth_label = {"quick": "Quick", "standard": "Standard", "deep": "Deep"}.get(depth, depth)
    key_label = "your key" if s["openrouter_key"] else "server key"
    return (
        f"Ready — send me a clinical scenario.\n\n"
        f"Current settings:\n"
        f"  🤖 Models  : {preset}\n"
        f"  📊 Depth   : {depth_label} ({n_branches} branches)\n"
        f"  🔑 API key : {key_label}\n\n"
        f"Tap ⚙️ Settings to change."
    )


# ── Start research flow ────────────────────────────────────────────────────────

async def _launch_research(update_or_message, uid: str, scenario: str) -> None:
    """
    Shared logic for starting a research run (from message handler or queue).
    update_or_message: a telegram Update or Message object.
    """
    msg = update_or_message.message if hasattr(update_or_message, "message") else update_or_message

    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    if _user_locks[uid].locked():
        await msg.reply_text("⏳ Already starting — please wait.")
        return

    async with _user_locks[uid]:
        if get_state(uid) != "idle":
            return

        # Stamp a run ID so stale background threads don't overwrite a newer run
        _run_ids[uid] = _run_ids.get(uid, 0) + 1
        my_run_id = _run_ids[uid]

        await msg.reply_text(
            "🔬 Analysing scenario…\n"
            "I'll show you the research plan in about a minute before starting the full search."
        )

        async def on_plan(plan_msg: str, plan_session: PlanSession) -> None:
            _plan_sessions[uid] = plan_session
            branches = plan_session.get_branches()
            await msg.reply_text(plan_msg, reply_markup=_kb_plan(branches))

        async def on_progress(stage: str, progress_msg: str, pct: int) -> None:
            if stage in ("bfs_start", "plan_confirmed", "done"):
                return
            if _run_ids.get(uid) != my_run_id:
                return  # this run was superseded
            await msg.reply_text(progress_msg)

        async def on_done(session_dir: Path) -> None:
            # If a newer run has started (or user cancelled), discard this result
            if _run_ids.get(uid) != my_run_id:
                return
            if get_state(uid) == "idle":
                return  # cancelled

            pdf_path = find_pdf_for_session(session_dir)
            md_path  = find_report_md_for_session(session_dir)

            summary = ""
            if md_path and md_path.exists():
                summary = extract_summary(md_path.read_text(encoding="utf-8"))

            try:
                await msg.reply_text(
                    "✅ *Research complete\\!\n\n" + escape_md(summary) +
                    "\n\n_Full report attached\\. Ask me follow\\-up questions\\._",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except Exception:
                await msg.reply_text(f"✅ Research complete!\n\n{summary}")

            if pdf_path and pdf_path.exists():
                with open(pdf_path, "rb") as f:
                    await msg.reply_document(document=f, filename=pdf_path.name,
                                             caption="CRAM-1 Clinical Research Brief")
            elif md_path and md_path.exists():
                with open(md_path, "rb") as f:
                    await msg.reply_document(document=f, filename=md_path.name,
                                             caption="CRAM-1 Clinical Research Brief")

            await msg.reply_text(
                "Ask follow-up questions about this research.",
                reply_markup=_kb_idle(),
            )

            # Auto-start queued scenario if any
            queued = get_queued_scenario(uid)
            if queued:
                set_queued_scenario(uid, None)
                await msg.reply_text(f"📥 Starting queued scenario:\n\"{queued[:100]}\"")
                await _launch_research(msg, uid, queued)

        async def on_error(error_msg: str) -> None:
            await msg.reply_text(
                f"❌ Research failed.\n\n{error_msg}\n\nTry again.",
                reply_markup=_kb_idle(),
            )

        await start_research(uid, scenario, on_plan, on_progress, on_done, on_error,
                             pdf=True, run_params=get_run_params(uid))


# ── Settings text input handler ───────────────────────────────────────────────

async def _handle_settings_text(update: Update, uid: str, text: str) -> None:
    state = _settings_state.pop(uid, None)

    if state == "awaiting_key":
        key = text.strip()
        if not (key.startswith("sk-or-") and len(key) > 20):
            await update.message.reply_text(
                "❌ That doesn't look like a valid OpenRouter key.\n"
                "Keys start with `sk-or-` — try again or tap Settings to cancel.",
            )
            _settings_state[uid] = "awaiting_key"  # keep waiting
            return
        set_user_settings(uid, openrouter_key=key)
        await update.message.reply_text("✅ API key saved! Your key will be used for all future research runs.")
        await update.message.reply_text(build_settings_message(uid), reply_markup=build_settings_keyboard())

    elif state == "awaiting_big_model":
        model = text.strip()
        _settings_pending.setdefault(uid, {})["model_big"] = model
        _settings_state[uid] = "awaiting_small_model"
        await update.message.reply_text(
            f"✅ Planning model: {model}\n\n"
            "Now send the research/search model name (small tasks).\n"
            "Example: google/gemini-2.0-flash-001",
        )

    elif state == "awaiting_small_model":
        model = text.strip()
        pending = _settings_pending.pop(uid, {})
        model_big = pending.get("model_big", "")
        set_user_settings(uid, model_big=model_big, model_small=model)
        await update.message.reply_text(
            f"✅ Custom models saved!\nPlanning : {model_big}\nResearch : {model}",
        )
        await update.message.reply_text(build_settings_message(uid), reply_markup=build_settings_keyboard())


# ── Message handler ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid   = str(update.effective_user.id)
    text  = (update.message.text or "").strip()
    state = get_state(uid)

    if not text:
        return

    # ── Settings text input ───────────────────────────────────────────────────
    if uid in _settings_state:
        await _handle_settings_text(update, uid, text)
        return

    # ── Plan confirmation: text commands (add/edit) ───────────────────────────
    if uid in _plan_sessions:
        plan = _plan_sessions[uid]
        lower = text.lower().strip()
        # Only handle add/edit here; go/skip/cancel are buttons
        if lower.startswith("add ") or lower.startswith("edit "):
            is_confirmed, reply = plan.apply_command(text)
            branches = plan.get_branches()
            await update.message.reply_text(
                reply + "\n\n" + format_plan_message(branches, plan.get_qa()),
                reply_markup=_kb_plan(branches),
            )
            if is_confirmed:
                _plan_sessions.pop(uid, None)
        else:
            await update.message.reply_text(
                "Use the buttons to skip branches or start research.\n"
                "You can also type `add <topic>` or `edit N <description>`.",
                reply_markup=_kb_plan(plan.get_branches()),
            )
        return

    # ── Researching ───────────────────────────────────────────────────────────
    if state == "researching":
        # Intent check: casual messages get a brief reply without offering queue
        if await classify(text) == "casual":
            await update.message.reply_text(
                "Research is still running — I'll message you when it's ready.",
                reply_markup=_kb_cancel(),
            )
            return
        # It's a new research scenario — offer queue
        _pending_scenarios[uid] = text
        scenario_running = get_scenario(uid) or "current scenario"
        await update.message.reply_text(
            f"⏳ Already researching: \"{scenario_running[:70]}\"\n\n"
            f"New scenario: \"{text[:70]}\"\n\n"
            "What would you like to do?",
            reply_markup=_kb_queue(text),
        )
        return

    # ── Chatting ──────────────────────────────────────────────────────────────
    if state == "chatting":
        # Only filter obvious greetings (≤2 words) — don't LLM-classify follow-up
        # questions since short clinical questions ("what about ketamine?") would
        # be incorrectly dropped as casual.
        if len(text.split()) <= 2:
            await update.message.reply_text(
                "Ask me a follow-up question about the research, or tap New Research to start fresh.",
                reply_markup=_kb_idle(),
            )
            return

        session_dir = get_session_dir(uid)
        if not session_dir or not session_dir.exists():
            set_idle(uid)
            await update.message.reply_text("Session not found.", reply_markup=_kb_idle())
            return

        await update.message.reply_text("🔍 Looking that up in the evidence…")
        loop = asyncio.get_event_loop()
        try:
            answer = await loop.run_in_executor(None, run_chat_query, session_dir, text)
        except Exception as e:
            logger.exception("Chat query failed")
            answer = f"Sorry, couldn't answer that.\nError: {e}"
        await _send(update, answer)
        return

    # ── Idle ──────────────────────────────────────────────────────────────────
    if await classify(text) == "casual":
        await update.message.reply_text(casual_reply())
        return

    await _launch_research(update, uid, text)


# ── Settings callback handler ─────────────────────────────────────────────────

async def _handle_settings_callback(query, uid: str, data: str) -> None:
    # Clear any pending text-input state if they navigate away
    sub = data[len("settings:"):]

    if sub == "open" or sub == "back_main":
        _settings_state.pop(uid, None)
        _settings_pending.pop(uid, None)
        try:
            await query.edit_message_text(
                build_settings_message(uid),
                reply_markup=build_settings_keyboard(),
            )
        except Exception:
            await query.message.reply_text(
                build_settings_message(uid),
                reply_markup=build_settings_keyboard(),
            )

    elif sub == "back":
        _settings_state.pop(uid, None)
        _settings_pending.pop(uid, None)
        await query.edit_message_reply_markup(reply_markup=None)

    elif sub == "key":
        _settings_state[uid] = "awaiting_key"
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🔑 Send your OpenRouter API key now.\n\n"
            "You can get one at openrouter.ai/keys\n"
            "Keys look like: `sk-or-v1-abc123...`\n\n"
            "_Your key is stored securely and only used for your requests._",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    elif sub == "models":
        try:
            await query.edit_message_text(
                "🤖 Choose a model preset\n\n"
                "DEFAULT uses the server's configured models.\n"
                "Custom presets require your own API key.",
                reply_markup=build_model_keyboard(),
            )
        except Exception:
            await query.message.reply_text(
                "Choose a model preset:",
                reply_markup=build_model_keyboard(),
            )

    elif sub == "depth":
        try:
            await query.edit_message_text(
                "📊 Choose report depth\n\n"
                "More branches = more thorough but slower.",
                reply_markup=build_depth_keyboard(),
            )
        except Exception:
            await query.message.reply_text(
                "Choose report depth:",
                reply_markup=build_depth_keyboard(),
            )

    elif sub == "reset":
        set_user_settings(uid, openrouter_key=None, model_big=None, model_small=None, report_depth="standard")
        _settings_state.pop(uid, None)
        _settings_pending.pop(uid, None)
        try:
            await query.edit_message_text(
                "✅ Settings reset to defaults.",
                reply_markup=build_settings_keyboard(),
            )
        except Exception:
            await query.message.reply_text("✅ Settings reset to defaults.", reply_markup=build_settings_keyboard())

    elif sub.startswith("model:"):
        preset_name = sub[len("model:"):]
        if preset_name == "CUSTOM":
            _settings_state[uid] = "awaiting_big_model"
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "✏️ Send the *planning model* name (big tasks, e.g. `anthropic/claude-opus-4-6`):\n\n"
                "_Browse models at openrouter.ai/models_",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            big, small = MODEL_PRESETS.get(preset_name, (None, None))
            set_user_settings(uid, model_big=big, model_small=small)
            label = preset_name if preset_name != "DEFAULT" else "DEFAULT (server config)"
            try:
                await query.edit_message_text(
                    f"✅ Model preset: {label}",
                    reply_markup=build_settings_keyboard(),
                )
            except Exception:
                await query.message.reply_text(f"✅ Model preset: {label}", reply_markup=build_settings_keyboard())

    elif sub.startswith("depth:"):
        depth = sub[len("depth:"):]
        set_user_settings(uid, report_depth=depth)
        labels = {"quick": "Quick (~8 min)", "standard": "Standard (~15 min)", "deep": "Deep (~25 min)"}
        label = labels.get(depth, depth)
        try:
            await query.edit_message_text(
                f"✅ Report depth: {label}",
                reply_markup=build_settings_keyboard(),
            )
        except Exception:
            await query.message.reply_text(f"✅ Report depth: {label}", reply_markup=build_settings_keyboard())


# ── Callback query handler (button taps) ──────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # dismiss the loading spinner

    uid  = str(update.effective_user.id)
    data = query.data or ""

    # ── Plan buttons ─────────────────────────────────────────────────────────
    if data.startswith("plan:"):
        plan = _plan_sessions.get(uid)
        if not plan:
            await query.edit_message_reply_markup(reply_markup=None)
            return

        if data == "plan:go":
            _plan_sessions.pop(uid, None)
            plan.apply_command("go")
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("✅ Starting research now…")

        elif data == "plan:cancel":
            _plan_sessions.pop(uid, None)
            plan.apply_command("cancel")
            set_idle(uid)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("Cancelled. Send a new scenario whenever you're ready.")

        elif data.startswith("plan:skip:"):
            n = data.split(":")[-1]
            _, reply = plan.apply_command(f"skip {n}")
            branches = plan.get_branches()
            try:
                await query.edit_message_text(
                    format_plan_message(branches, plan.get_qa()),
                    reply_markup=_kb_plan(branches),
                )
            except Exception:
                await query.message.reply_text(
                    format_plan_message(branches, plan.get_qa()),
                    reply_markup=_kb_plan(branches),
                )
        return

    # ── Queue buttons ─────────────────────────────────────────────────────────
    if data.startswith("queue:"):
        pending = _pending_scenarios.get(uid, "")

        if data == "queue:add":
            if pending:
                set_queued_scenario(uid, pending)
                _pending_scenarios.pop(uid, None)
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(
                    f"📥 Queued: \"{pending[:80]}\"\nI'll start it automatically when current research finishes."
                )
            else:
                await query.edit_message_reply_markup(reply_markup=None)

        elif data == "queue:cancel_current":
            _pending_scenarios.pop(uid, None)
            _run_ids[uid] = _run_ids.get(uid, 0) + 1  # invalidate any running thread
            set_idle(uid)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "Current research cancelled. Send your new scenario."
            )

        elif data == "queue:dismiss":
            _pending_scenarios.pop(uid, None)
            await query.edit_message_reply_markup(reply_markup=None)
        return

    # ── Settings buttons ──────────────────────────────────────────────────────
    if data.startswith("settings:"):
        await _handle_settings_callback(query, uid, data)
        return

    # ── General action buttons ────────────────────────────────────────────────
    if data.startswith("action:"):
        action = data.split(":", 1)[1]

        if action == "new":
            _plan_sessions.pop(uid, None)
            _run_ids[uid] = _run_ids.get(uid, 0) + 1  # invalidate any running thread
            set_idle(uid)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                _ready_message(uid),
                reply_markup=_kb_idle(),
            )

        elif action == "cancel":
            _plan_sessions.pop(uid, None)
            _run_ids[uid] = _run_ids.get(uid, 0) + 1  # invalidate any running thread
            set_idle(uid)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "Research cancelled. Send a new scenario whenever you're ready."
            )

        elif action == "history":
            from cram.pipeline.chat import list_loadable_sessions
            import cram.config as cfg_mod
            sessions = list_loadable_sessions(cfg_mod.DATA_DIR)
            if not sessions:
                await query.message.reply_text("No past sessions found.")
                return
            lines = ["📚 Past sessions — tap to load for Q&A:\n"]
            rows = []
            for i, s in enumerate(sessions[:8], 1):
                date  = s.get("date", "?")[:16]
                hint  = (s.get("scenario_hint") or "")[:55]
                label = f"{date}  {hint}" if hint else date
                lines.append(f"{i}. {label}")
                session_path = str(s.get("path", ""))
                rows.append([InlineKeyboardButton(
                    f"💬 Load #{i}", callback_data=f"action:load_session:{i-1}"
                )])
            # Store session list temporarily for load callbacks
            _pending_scenarios[f"{uid}_sessions"] = [str(s["path"]) for s in sessions[:8]]
            rows.append([InlineKeyboardButton("← Back", callback_data="action:new")])
            await query.message.reply_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(rows),
            )

        elif action.startswith("load_session:"):
            idx = int(action.split(":")[-1])
            session_paths = _pending_scenarios.get(f"{uid}_sessions", [])
            if idx >= len(session_paths):
                await query.message.reply_text("Session not found.")
                return
            session_dir = Path(session_paths[idx])
            if not session_dir.exists():
                await query.message.reply_text("Session directory no longer exists.")
                return
            from bot.session_map import set_chatting
            set_chatting(uid, session_dir)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"✅ Session loaded. Ask me any follow-up questions about this research.",
                reply_markup=_kb_idle(),
            )


# ── /start command (the only slash command doctors need) ──────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name or "Doctor"
    await update.message.reply_text(
        f"Hello {name} 👋\n\n"
        "I'm CRAM-1 — Clinical Research Agent.\n\n"
        "Send me a clinical scenario and I'll search the medical literature and send you "
        "a structured evidence brief with safety review (~15 minutes).\n\n"
        "Examples:\n"
        "• 65M cirrhosis, planned Whipple, on rivaroxaban\n"
        "• 38F HIV+ on dolutegravir, starting rifampicin for TB\n"
        "• 72M CKD stage 3b on metformin, scheduled for total knee replacement\n\n"
        "I'll show you the research plan before starting — you can skip branches or add directions.\n\n"
        + _ready_message(str(update.effective_user.id)),
        reply_markup=_kb_idle(),
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set. Add it to bot/.env")
        sys.exit(1)

    init_db()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("CRAM-1 Telegram bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
