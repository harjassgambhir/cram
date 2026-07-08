"""
bot/settings.py — Per-user settings for the CRAM-1 Telegram bot.

Settings:
  - openrouter_key  : user's own OpenRouter API key (optional)
  - model preset    : DEFAULT / BUDGET / BALANCED / POWER / CUSTOM
  - report depth    : quick / standard / deep

Model presets:
  DEFAULT   — use server's configured models
  BUDGET    — haiku (big) + gemini-flash (small)  ~$0.05/run
  BALANCED  — sonnet (big) + gemini-flash (small) ~$0.30/run
  POWER     — opus (big) + sonnet (small)         ~$2.00/run
  CUSTOM    — user provides both model names manually
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.session_map import get_user_settings, set_user_settings


# ── Model presets ──────────────────────────────────────────────────────────────

MODEL_PRESETS = {
    "DEFAULT":  (None, None),
    "BUDGET":   ("anthropic/claude-haiku-4-5",  "google/gemini-2.0-flash-001"),
    "BALANCED": ("anthropic/claude-sonnet-4-6", "google/gemini-2.0-flash-001"),
    "POWER":    ("anthropic/claude-opus-4-6",   "anthropic/claude-sonnet-4-6"),
}

DEPTH_PRESETS = {
    "quick":    (4, 2),   # (n_branches, dfs_depth)
    "standard": (6, 3),
    "deep":     (8, 4),
}


def detect_model_preset(model_big: str | None, model_small: str | None) -> str:
    """Reverse-map stored models back to a preset name, or 'CUSTOM'."""
    for name, (big, small) in MODEL_PRESETS.items():
        if model_big == big and model_small == small:
            return name
    if model_big or model_small:
        return "CUSTOM"
    return "DEFAULT"


# ── Settings message ───────────────────────────────────────────────────────────

def build_settings_message(uid: str) -> str:
    """Return plain-text settings summary (no MarkdownV2 needed)."""
    s = get_user_settings(uid)
    key_status = "Set (your key)" if s["openrouter_key"] else "Not set (server key)"
    preset = detect_model_preset(s["model_big"], s["model_small"])
    depth = s["report_depth"] or "standard"

    if preset == "CUSTOM":
        model_line = (
            f"  Planning : {s['model_big'] or 'default'}\n"
            f"  Research : {s['model_small'] or 'default'}"
        )
        model_header = "Models    : CUSTOM"
    else:
        model_line = ""
        model_header = f"Models    : {preset}"

    depth_info = {
        "quick":    "Quick — 4 branches, ~8 min",
        "standard": "Standard — 6 branches, ~15 min",
        "deep":     "Deep — 8 branches, ~25 min",
    }

    lines = [
        "⚙️ Settings\n",
        f"🔑 API Key : {key_status}",
        f"🤖 {model_header}",
    ]
    if model_line:
        lines.append(model_line)
    lines.append(f"📊 Depth   : {depth_info.get(depth, depth)}")
    lines.append("\nChanges take effect on your next research run.")
    return "\n".join(lines)


# ── Keyboards ──────────────────────────────────────────────────────────────────

def build_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 API Key",      callback_data="settings:key")],
        [InlineKeyboardButton("🤖 Models",       callback_data="settings:models")],
        [InlineKeyboardButton("📊 Report depth", callback_data="settings:depth")],
        [InlineKeyboardButton("🔄 Reset to defaults", callback_data="settings:reset")],
        [InlineKeyboardButton("← Back",          callback_data="settings:back")],
    ])


def build_model_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("DEFAULT (server config)",     callback_data="settings:model:DEFAULT")],
        [InlineKeyboardButton("💚 BUDGET  — ~$0.05/run",    callback_data="settings:model:BUDGET")],
        [InlineKeyboardButton("💛 BALANCED — ~$0.30/run",   callback_data="settings:model:BALANCED")],
        [InlineKeyboardButton("🔴 POWER   — ~$2.00/run",    callback_data="settings:model:POWER")],
        [InlineKeyboardButton("✏️ CUSTOM (enter manually)", callback_data="settings:model:CUSTOM")],
        [InlineKeyboardButton("← Back",                     callback_data="settings:back_main")],
    ])


def build_depth_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Quick    — 4 branches ~8 min",   callback_data="settings:depth:quick")],
        [InlineKeyboardButton("⚖️ Standard — 6 branches ~15 min", callback_data="settings:depth:standard")],
        [InlineKeyboardButton("🔬 Deep     — 8 branches ~25 min", callback_data="settings:depth:deep")],
        [InlineKeyboardButton("← Back",                           callback_data="settings:back_main")],
    ])


# ── Helper for runner.py ───────────────────────────────────────────────────────

def get_run_params(uid: str) -> dict:
    """
    Return kwargs to pass to start_research() / _run() based on user settings.
    Keys: api_key, model_big, model_small, n_branches, dfs_depth
    """
    s = get_user_settings(uid)
    n_branches, dfs_depth = DEPTH_PRESETS.get(s["report_depth"] or "standard", (6, 3))
    return {
        "api_key":    s["openrouter_key"],
        "model_big":  s["model_big"],
        "model_small": s["model_small"],
        "n_branches": n_branches,
        "dfs_depth":  dfs_depth,
    }
