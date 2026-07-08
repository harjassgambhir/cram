"""
conftest.py — Shared pytest fixtures.
All tests can use these without importing.
"""
import os
import pathlib
import tempfile

import pytest


# ── Set test API key before any import touches config ─────────────────────────
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")


# ── Temporary data directory ───────────────────────────────────────────────────

@pytest.fixture
def tmp_data_dir():
    """Isolated temp directory for each test. Cleaned up automatically."""
    with tempfile.TemporaryDirectory() as td:
        yield pathlib.Path(td)


@pytest.fixture
def query_cache(tmp_data_dir):
    from cram.search.base import QueryCache
    return QueryCache(tmp_data_dir)


@pytest.fixture
def persistent_memory(tmp_data_dir):
    from cram.memory.persistent import PersistentMemory
    return PersistentMemory(tmp_data_dir)


@pytest.fixture
def research_memory(tmp_data_dir):
    from cram.memory.store import ResearchMemory
    session_dir = tmp_data_dir / "session_test"
    return ResearchMemory(session_dir)


@pytest.fixture
def session_search(tmp_data_dir):
    from cram.memory.session_search import SessionSearch
    return SessionSearch(tmp_data_dir)


@pytest.fixture
def branch_checkpoint(tmp_data_dir):
    from cram.memory.store import BranchCheckpoint
    session_dir = tmp_data_dir / "session_cp"
    session_dir.mkdir()
    return BranchCheckpoint(session_dir)


# Profile fixtures removed — profiles eliminated in favour of fully dynamic LLM guidance.


# ── LLM mock helpers ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_response():
    """Factory: returns a mock requests.Response with JSON content."""
    from unittest.mock import MagicMock

    def _make(content: str, pt: int = 100, ct: int = 50):
        m = MagicMock()
        m.status_code = 200
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct},
        }
        return m

    return _make


@pytest.fixture
def patch_llm(mock_llm_response):
    """Patches requests.post to return a fixed LLM response. Usage:
        def test_something(patch_llm):
            with patch_llm('{"key": "value"}') as mock:
                result = some_function()
    """
    from unittest.mock import patch

    class _Patcher:
        def __call__(self, content: str):
            return patch(
                "requests.post",
                return_value=mock_llm_response(content),
            )

    return _Patcher()


# ── Config override for tests ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_rate_limit_sleep():
    """Zero out sleep delays globally so tests don't take 14+ seconds."""
    import cram.config as cfg
    original = cfg.RATE_LIMIT_SLEEP
    cfg.RATE_LIMIT_SLEEP = 0
    yield
    cfg.RATE_LIMIT_SLEEP = original
