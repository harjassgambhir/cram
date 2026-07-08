"""
memory/session_search.py — SQLite FTS5 index of past research sessions.
Enables recall of relevant prior research when a new case is described.
"""

import sqlite3
from pathlib import Path
import cram.config as _cfg
from cram.config import DATA_DIR


class SessionSearch:
    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            data_dir = _cfg.DATA_DIR
        self.db_path = data_dir / "sessions.db"
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        # Check if table exists and has the right number of columns; recreate if not.
        try:
            cols = conn.execute("SELECT * FROM sessions_fts LIMIT 0").description or []
            if len(cols) < 6:
                conn.execute("DROP TABLE sessions_fts")
                conn.commit()
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet — will be created below
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                scenario, summary, report_path, date, source_count, field
            )
        """)
        conn.commit()
        conn.close()

    def add_session(self, scenario: str, summary: str, report_path: str,
                    date: str, source_count: int, field: str = "surgery"):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT INTO sessions_fts VALUES (?,?,?,?,?,?)",
            (scenario, summary, report_path, date, source_count, field)
        )
        conn.commit()
        conn.close()

    def search(self, query: str, limit: int = 5) -> list[dict]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        safe_q = " ".join(f'"{w}"' for w in query.split() if len(w) > 2) or query
        try:
            rows = conn.execute(
                "SELECT scenario,summary,report_path,date,source_count,field,rank "
                "FROM sessions_fts WHERE sessions_fts MATCH ? ORDER BY rank LIMIT ?",
                (safe_q, limit)
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        conn.close()
        return [dict(r) for r in rows]

    def list_sessions(self, limit: int = 20, field: str = "") -> list[dict]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        if field:
            rows = conn.execute(
                "SELECT scenario,date,source_count,report_path,field FROM sessions_fts "
                "WHERE field=? ORDER BY date DESC LIMIT ?", (field, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT scenario,date,source_count,report_path,field FROM sessions_fts "
                "ORDER BY date DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
