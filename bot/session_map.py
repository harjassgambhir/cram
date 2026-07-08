"""
bot/session_map.py — persistent user state for the CRAM-1 Telegram bot.

Maps telegram_user_id → { state, session_dir, scenario }
States:  idle | researching | chatting
Backed by SQLite in ~/.cram/bot_sessions.db
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

# One lock per db file — protects against concurrent writes from multiple handlers
_lock = threading.Lock()


def _db_path() -> Path:
    from cram.config import DATA_DIR
    return DATA_DIR / "bot_sessions.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Call once at bot startup."""
    with _lock, _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id     TEXT PRIMARY KEY,
                state           TEXT NOT NULL DEFAULT 'idle',
                session_dir     TEXT,
                scenario        TEXT,
                queued_scenario TEXT,
                updated_at      REAL DEFAULT (strftime('%s','now'))
            )
        """)
        # Add queued_scenario column if upgrading from older schema
        try:
            conn.execute("ALTER TABLE users ADD COLUMN queued_scenario TEXT")
        except Exception:
            pass

        # Any "researching" state from a previous process is stale — reset to idle
        conn.execute("UPDATE users SET state = 'idle' WHERE state = 'researching'")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                telegram_id     TEXT PRIMARY KEY,
                openrouter_key  TEXT,
                model_big       TEXT,
                model_small     TEXT,
                report_depth    TEXT DEFAULT 'standard',
                updated_at      REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.commit()


# ── State reads ────────────────────────────────────────────────────────────────

def get_state(telegram_id: str) -> str:
    """Return current state for user, defaulting to 'idle'."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT state FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return row["state"] if row else "idle"


def get_session_dir(telegram_id: str) -> Optional[Path]:
    """Return active session_dir Path for user, or None."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT session_dir FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    if row and row["session_dir"]:
        return Path(row["session_dir"])
    return None


def get_scenario(telegram_id: str) -> Optional[str]:
    """Return the scenario that was submitted for the current/last run."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT scenario FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return row["scenario"] if row else None


def get_queued_scenario(telegram_id: str) -> Optional[str]:
    """Return a scenario queued to run after the current one finishes."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT queued_scenario FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    return row["queued_scenario"] if row else None


def set_queued_scenario(telegram_id: str, scenario: Optional[str]) -> None:
    with _lock, _conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, queued_scenario)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                queued_scenario = excluded.queued_scenario,
                updated_at      = strftime('%s','now')
        """, (telegram_id, scenario))
        conn.commit()


# ── State writes ───────────────────────────────────────────────────────────────

def set_researching(telegram_id: str, scenario: str) -> None:
    with _lock, _conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, state, scenario, session_dir)
            VALUES (?, 'researching', ?, NULL)
            ON CONFLICT(telegram_id) DO UPDATE SET
                state      = 'researching',
                scenario   = excluded.scenario,
                session_dir = NULL,
                updated_at = strftime('%s','now')
        """, (telegram_id, scenario))
        conn.commit()


def set_chatting(telegram_id: str, session_dir: Path) -> None:
    with _lock, _conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, state, session_dir)
            VALUES (?, 'chatting', ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                state       = 'chatting',
                session_dir = excluded.session_dir,
                updated_at  = strftime('%s','now')
        """, (telegram_id, str(session_dir)))
        conn.commit()


def get_user_settings(telegram_id: str) -> dict:
    """Return user settings dict. Keys: openrouter_key, model_big, model_small, report_depth."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT openrouter_key, model_big, model_small, report_depth "
            "FROM user_settings WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    if row:
        return {
            "openrouter_key": row["openrouter_key"],
            "model_big":      row["model_big"],
            "model_small":    row["model_small"],
            "report_depth":   row["report_depth"] or "standard",
        }
    return {"openrouter_key": None, "model_big": None, "model_small": None, "report_depth": "standard"}


def set_user_settings(telegram_id: str, **kwargs) -> None:
    """Update one or more user settings fields."""
    valid = {"openrouter_key", "model_big", "model_small", "report_depth"}
    fields = {k: v for k, v in kwargs.items() if k in valid}
    if not fields:
        return
    cols = list(fields.keys())
    vals = list(fields.values())
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in cols)
    placeholders = ", ".join("?" for _ in range(len(cols) + 1))
    with _lock, _conn() as conn:
        conn.execute(f"""
            INSERT INTO user_settings (telegram_id, {', '.join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(telegram_id) DO UPDATE SET
                {set_clause},
                updated_at = strftime('%s','now')
        """, [telegram_id] + vals)
        conn.commit()


def set_idle(telegram_id: str) -> None:
    with _lock, _conn() as conn:
        conn.execute("""
            INSERT INTO users (telegram_id, state)
            VALUES (?, 'idle')
            ON CONFLICT(telegram_id) DO UPDATE SET
                state      = 'idle',
                updated_at = strftime('%s','now')
        """, (telegram_id,))
        conn.commit()
