"""
search/base.py — QueryCache, dedup, cached_search decorator.
[1.2] FIXED: SQLite WAL mode + timeout to prevent 'database is locked' under parallel workers.
[7]  Cache keyed on hash(source + query).
"""

import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from functools import wraps


class RateLimiter:
    """
    Thread-safe minimum-interval limiter. Serialises calls across all worker
    threads so a rate-capped API (e.g. NCBI E-utilities: 3 req/s without a key)
    is never exceeded — far cheaper than colliding into 429s and exponential backoff.
    """

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now   = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()

import cram.config as _cfg
from cram.config import RESULTS_PER_SOURCE
from cram.log import log, dim, stat


# ── [1.2] SQLite WAL connection factory ───────────────────────────────────────

def _wal_conn(db_path: Path) -> sqlite3.Connection:
    """Open a connection with WAL journal mode to safely allow parallel readers/writers."""
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class QueryCache:
    """SQLite-backed cache for search results. Key = SHA-256(source + query)."""

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            data_dir = _cfg.DATA_DIR
        self.db_path = data_dir / "query_cache.db"
        self._init_db()

    def _init_db(self):
        conn = _wal_conn(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                results TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _key(self, source: str, query: str) -> str:
        return hashlib.sha256(f"{source}::{query}".encode()).hexdigest()

    def get(self, source: str, query: str) -> Optional[list]:
        key  = self._key(source, query)
        conn = _wal_conn(self.db_path)
        row  = conn.execute("SELECT results FROM cache WHERE key=?", (key,)).fetchone()
        conn.close()
        if row:
            stat("cache_hits")
            return json.loads(row[0])
        return None

    def set(self, source: str, query: str, results: list):
        key  = self._key(source, query)
        conn = _wal_conn(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, results, created_at) VALUES (?,?,?)",
            (key, json.dumps(results, ensure_ascii=False), datetime.now().isoformat())
        )
        conn.commit()
        conn.close()

    def clear(self, older_than_days: int = 30):
        conn = _wal_conn(self.db_path)
        conn.execute(
            "DELETE FROM cache WHERE created_at < datetime('now', ?)",
            (f"-{older_than_days} days",)
        )
        conn.commit()
        conn.close()


# Module-level singleton
_query_cache: "QueryCache | None" = None


def _get_cache() -> "QueryCache":
    """Lazy singleton — reads _cfg.DATA_DIR at first call so tests can override it."""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCache(_cfg.DATA_DIR)
    return _query_cache


# ── Deduplication ──────────────────────────────────────────────────────────────

def dedup_results(results: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for r in results:
        key = (r.get("pmid") or r.get("doi") or r.get("nct_id")
               or r.get("url", "").split("?")[0])
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(r)
    return unique


# ── [7] cached_search decorator ───────────────────────────────────────────────

def cached_search(source_name: str):
    """
    Decorator: wraps any tool_* function with QueryCache + dedup.
    Usage:
        @cached_search("PubMed")
        def tool_pubmed(query: str, max_results: int = RESULTS_PER_SOURCE) -> list[dict]:
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(query: str, max_results: int = RESULTS_PER_SOURCE, **kwargs) -> list[dict]:
            cached = _get_cache().get(source_name, query)
            if cached is not None:
                log(dim(f"     💾 {source_name} cache hit ← \"{query[:60]}\""))
                return cached
            results = fn(query, max_results, **kwargs)
            results = dedup_results(results)
            if results:
                _get_cache().set(source_name, query, results)
            stat("sources_fetched")
            return results
        return wrapper
    return decorator


def get_cache() -> QueryCache:
    return _get_cache()


def reset_cache():
    """Force the query cache singleton to reinitialise on next access.
    Call this in tests after patching cfg.DATA_DIR.
    """
    global _query_cache
    _query_cache = None
