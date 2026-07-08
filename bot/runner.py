"""
bot/runner.py — runs CRAM-1 research in a background thread with:
  - plan confirmation sent to Telegram before DFS starts
  - progress updates sent during the run
"""

import asyncio
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Awaitable, Optional

import cram.config as cfg
from cram.run import run_research
from cram.provider.openrouter import set_thread_overrides, clear_thread_overrides
from bot.session_map import set_researching, set_chatting, set_idle
from bot.settings import get_run_params


# ── Time estimates per stage ───────────────────────────────────────────────────
# These are rough for a 6-branch run; shown to users as "~X min remaining"
_STAGE_MINS_LEFT = {
    "bfs_start":       15,
    "bfs_done":        14,
    "plan_confirmed":  13,
    "branch_done":     None,  # computed dynamically
    "dfs_done":         4,
    "synthesis_start":  3,
    "report_written":   1,
    "done":             0,
}

_STAGE_EMOJI = {
    "bfs_start":       "🔍",
    "bfs_done":        "📋",
    "plan_confirmed":  "✅",
    "branch_done":     "🔬",
    "dfs_done":        "🧠",
    "synthesis_start": "📝",
    "report_written":  "📄",
    "done":            "✅",
}


# ── Plan confirmation ──────────────────────────────────────────────────────────

class PlanSession:
    """
    Manages the plan confirmation handshake between the background research
    thread and the Telegram message handler.

    Flow:
      1. background thread calls wait_for_plan(branches, qa) — blocks
      2. bot sends plan to Telegram, sets _branches, sets _ready event
      3. user can send commands: skip N / add <topic> / edit N <desc> / go
      4. when user sends "go" or "yes", bot calls confirm() — unblocks thread
      5. background thread resumes with (possibly modified) branches
    """

    def __init__(self):
        self._ready   = threading.Event()
        self._branches: list = []
        self._qa: dict = {}
        self._lock = threading.Lock()

    # Called from background thread ──────────────────────────────────────────

    def wait_for_plan(self, branches: list, question_analysis: dict) -> list:
        """Block until the user explicitly confirms via Start Research or Cancel."""
        with self._lock:
            self._branches = list(branches)
            self._qa = question_analysis or {}
        self._ready.wait()  # wait indefinitely — no auto-start
        with self._lock:
            return list(self._branches)

    # Called from Telegram handler ───────────────────────────────────────────

    def get_branches(self) -> list:
        with self._lock:
            return list(self._branches)

    def get_qa(self) -> dict:
        with self._lock:
            return dict(self._qa)

    def apply_command(self, cmd: str) -> tuple[bool, str]:
        """
        Apply a plan command from the user.
        Returns (is_final_confirm, response_message).
        """
        cmd = cmd.strip()
        lower = cmd.lower()

        if lower in ("go", "yes", "y", "ok", "proceed", "confirm", "start"):
            self._ready.set()
            return True, "Research starting now!"

        with self._lock:
            branches = self._branches

            if lower.startswith("skip "):
                try:
                    n = int(lower[5:].strip())
                    before = len(branches)
                    self._branches = [b for b in branches
                                      if b.get("branch_id") != n]
                    if len(self._branches) < before:
                        return False, f"✅ Branch {n} removed. Send *go* to start, or make more changes."
                    return False, f"Branch {n} not found."
                except ValueError:
                    return False, "Usage: skip N (e.g. skip 3)"

            if lower.startswith("add "):
                topic = cmd[4:].strip()
                new_id = max((b.get("branch_id", 0) for b in branches), default=0) + 1
                self._branches.append({
                    "branch_id":       new_id,
                    "angle":           topic,
                    "rationale":       "Added by user",
                    "primary_query":   topic[:60],
                    "followup_queries": [],
                })
                return False, f"✅ Branch added: \"{topic}\". Send *go* to start."

            if lower.startswith("edit "):
                parts = cmd[5:].split(None, 1)
                if len(parts) == 2:
                    try:
                        n = int(parts[0])
                        desc = parts[1].strip()
                        for b in self._branches:
                            if b.get("branch_id") == n:
                                b["angle"] = desc
                                b["primary_query"] = desc[:60]
                                return False, f"✅ Branch {n} updated to: \"{desc}\". Send *go* to start."
                        return False, f"Branch {n} not found."
                    except ValueError:
                        pass
                return False, "Usage: edit N <new description>"

        return False, (
            "Commands:\n"
            "• *go* — start research with this plan\n"
            "• *skip N* — remove branch N\n"
            "• *add <topic>* — add a research direction\n"
            "• *edit N <desc>* — change branch N's focus"
        )


def format_plan_message(branches: list, question_analysis: dict) -> str:
    """Format the research plan as a plain-text Telegram message."""
    qa = question_analysis or {}
    qtype = qa.get("question_type", "").replace("_", " ").title()
    practitioner = qa.get("practitioner_title", "")

    lines = ["📋 Research Plan"]
    if qtype:
        lines.append(f"Type: {qtype}")
    if practitioner:
        lines.append(f"For: {practitioner}")
    lines.append("")

    for b in branches:
        bid       = b.get("branch_id", "?")
        angle     = b.get("angle", "")[:80]
        rationale = b.get("rationale", "")[:120]
        query     = b.get("primary_query", "")[:70]
        followups = b.get("followup_queries", [])

        lines.append(f"[{bid}] {angle}")
        if rationale:
            lines.append(f"  ↳ {rationale}")
        lines.append(f"  🔍 {query}")
        for fq in followups[:2]:
            lines.append(f"  • {fq[:70]}")
        lines.append("")

    lines.append("Use the buttons below, or type:")
    lines.append("  add <topic> — add a direction")
    lines.append("  edit N <new description> — change a branch")

    return "\n".join(lines)


def _format_error(exc: Exception) -> str:
    """Turn an exception into a short, user-friendly message for Telegram."""
    from cram.provider.openrouter import CreditExhaustedError, ModelForbiddenError
    import requests

    if isinstance(exc, CreditExhaustedError):
        return (
            "💳 OpenRouter credits exhausted.\n\n"
            "Add credits at openrouter.ai/credits and try again."
        )
    if isinstance(exc, ModelForbiddenError):
        return (
            "🚫 Model access error (403 Forbidden).\n\n"
            + str(exc)
            + "\n\nTap ⚙️ Settings to switch to a different model."
        )
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else "?"
        return f"⚠️ API error (HTTP {status}).\n\nPlease try again in a moment."
    if isinstance(exc, requests.exceptions.Timeout):
        return "⏱️ Request timed out — the AI provider took too long. Please try again."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "🌐 Connection error — couldn't reach the AI provider. Check your network and try again."
    # Unknown error — show a short version, not the full traceback
    return f"❌ Unexpected error: {type(exc).__name__}: {str(exc)[:300]}"


# ── Main runner ────────────────────────────────────────────────────────────────

async def start_research(
    telegram_id: str,
    scenario: str,
    on_plan: Callable[[str, "PlanSession"], Awaitable[None]],
    on_progress: Callable[[str, str, int], Awaitable[None]],
    on_done: Callable[[Path], Awaitable[None]],
    on_error: Callable[[str], Awaitable[None]],
    pdf: bool = True,
    run_params: Optional[dict] = None,
) -> None:
    """
    Kick off a CRAM-1 research run in a thread executor.

    on_plan(plan_message, plan_session)  — called when plan is ready for confirmation
    on_progress(stage, message, pct)     — called at each pipeline stage (throttled)
    on_done(session_dir)                 — called when research completes
    on_error(message)                    — called on failure
    """
    set_researching(telegram_id, scenario)
    loop = asyncio.get_event_loop()

    # Resolve per-user run params (API key, model overrides, depth)
    _run_params = run_params or get_run_params(telegram_id)

    plan_session = PlanSession()
    _last_progress_time = [0.0]
    _total_branches = [_run_params.get("n_branches", cfg.BFS_BRANCHES)]

    def _plan_callback(branches: list, question_analysis: dict) -> list:
        """Called from background thread — send plan to Telegram, wait for confirmation."""
        _total_branches[0] = len(branches)
        plan_msg = format_plan_message(branches, question_analysis)
        # Wait up to 60s for the Telegram message to be sent (network can be slow)
        try:
            asyncio.run_coroutine_threadsafe(
                on_plan(plan_msg, plan_session), loop
            ).result(timeout=60)
        except Exception as e:
            # If sending the plan message fails, proceed without confirmation
            import logging
            logging.getLogger("cram-bot").warning(f"Plan send failed: {e} — proceeding auto")
            plan_session._ready.set()
        # Block until user confirms (or times out after 10 min)
        return plan_session.wait_for_plan(branches, question_analysis)

    def _progress_callback(stage: str, detail: str, pct: int) -> None:
        """Called from background thread — send progress to Telegram (throttled)."""
        now = time.time()
        # Branch updates: send every branch; other stages: max 1 per 90s
        if stage != "branch_done" and now - _last_progress_time[0] < 90:
            return
        _last_progress_time[0] = now

        if stage == "branch_done":
            # Extract N/M from detail
            emoji = _STAGE_EMOJI.get(stage, "🔬")
            # Compute remaining time: ~2.5 min per remaining branch
            done_match = [p for p in detail.split() if "/" in p]
            if done_match:
                try:
                    done, total = done_match[0].split("/")
                    remaining = int(total) - int(done)
                    mins = max(1, remaining * 2 + 3)  # +3 for synthesis
                    msg = f"{emoji} {detail}\n~{mins} min remaining"
                except Exception:
                    msg = f"{emoji} {detail}"
            else:
                msg = f"{emoji} {detail}"
        else:
            emoji = _STAGE_EMOJI.get(stage, "⚙️")
            mins  = _STAGE_MINS_LEFT.get(stage)
            if mins is not None and mins > 0:
                msg = f"{emoji} {detail}\n~{mins} min remaining"
            elif mins == 0:
                msg = f"{emoji} {detail}"
            else:
                msg = f"{emoji} {detail}"

        asyncio.run_coroutine_threadsafe(
            on_progress(stage, msg, pct), loop
        )

    def _run() -> Path:
        # Apply per-user model / API key overrides for this thread
        set_thread_overrides(
            api_key=_run_params.get("api_key"),
            model_big=_run_params.get("model_big"),
            model_small=_run_params.get("model_small"),
        )
        try:
            run_research(
                scenario=scenario,
                output_file=None,
                auto=True,
                patient_profile="",
                enter_chat=False,
                pdf=pdf,
                progress_callback=_progress_callback,
                plan_callback=_plan_callback,
                n_branches=_run_params.get("n_branches"),
                dfs_depth=_run_params.get("dfs_depth"),
            )
        finally:
            clear_thread_overrides()
        dirs = sorted(
            cfg.DATA_DIR.glob("session_*"),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if not dirs:
            raise RuntimeError("No session dir found after research")
        return dirs[0]

    def _done_callback(future: asyncio.Future) -> None:
        # This callback runs in the event loop thread — use create_task, not run_coroutine_threadsafe
        if future.exception():
            exc = future.exception()
            set_idle(telegram_id)
            loop.create_task(on_error(_format_error(exc)))
        else:
            session_dir = future.result()
            set_chatting(telegram_id, session_dir)
            loop.create_task(on_done(session_dir))

    future = loop.run_in_executor(None, _run)
    future.add_done_callback(_done_callback)


def run_chat_query(session_dir: Path, question: str) -> str:
    """Synchronous single-turn chat against a loaded session (run in executor)."""
    from cram.pipeline.chat import load_session_context
    from cram.pipeline.compactor import compact
    from cram.provider.openrouter import llm
    from cram.config import CHAT_SYSTEM

    context, _ = load_session_context(session_dir)
    if not context.strip():
        return "No research evidence found for this session."

    if len(context) > 18000:
        context = compact(context, label="session context", min_chars=18000)

    system = (
        CHAT_SYSTEM
        + "\n\n══════════════════════════════════════════\n"
        "LOADED SESSION EVIDENCE\n"
        "══════════════════════════════════════════\n\n"
        + context
        + "\n\n══════════════════════════════════════════\n"
        "If you cannot answer from the above evidence, say so explicitly "
        "and suggest what additional research would help.\n"
        "══════════════════════════════════════════\n"
    )

    return llm(
        [{"role": "user", "content": question}],
        system=system,
        label="bot chat",
        phase="chat",
        temperature=0.2,
    )
