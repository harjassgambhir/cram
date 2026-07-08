"""
memory/store.py — Session-level research memory and write-ahead log.

ResearchMemory:
  Layer 1: research_index.md  — pointer index
  Layer 2: branch_{id}.md    — evidence per branch
  Layer 3: raw_results.jsonl — all raw results (grep target)
  [9] Thread-safe writes via _write_lock (OpenClaw serial queue)

BranchCheckpoint:
  pending_branches.json — WAL for crash recovery [10]
"""

import json
import threading
from pathlib import Path
from typing import Optional

from cram.log import log, dim, green, yellow, red


class ResearchMemory:
    """3-layer session memory with mutex-protected writes."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.index_path  = session_dir / "research_index.md"
        self.raw_path    = session_dir / "raw_results.jsonl"
        self._write_lock = threading.Lock()   # [9] OpenClaw serial queue
        self.index: dict[str, str] = {}
        self._write_index_header()
        self._init_raw_file()

    def _write_index_header(self):
        if not self.index_path.exists():
            self.index_path.write_text(
                "# Research Index\n"
                "# branch_id | angle | file | findings | status\n\n",
                encoding="utf-8"
            )

    def _init_raw_file(self):
        if not self.raw_path.exists():
            self.raw_path.write_text("", encoding="utf-8")

    def append_raw_results(self, results: list[dict], query: str):
        with self._write_lock:
            try:
                with open(self.raw_path, "a", encoding="utf-8") as f:
                    for r in results:
                        f.write(json.dumps({"query": query, **r}, ensure_ascii=False) + "\n")
            except OSError as e:
                log(yellow(f"  [MEM] Raw write failed: {e}"))

    def grep_raw_results(self, term: str) -> list[dict]:
        """[11] Layer 3 grep — used by verifier before calling REMOVE."""
        matches    = []
        term_lower = term.lower()
        try:
            with open(self.raw_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if (term_lower in entry.get("title",   "").lower()
                                or term_lower in entry.get("snippet", "").lower()
                                or term_lower in str(entry.get("pmid", ""))):
                            matches.append(entry)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return matches

    def write_branch_evidence(self, branch_id, angle: str, content: str) -> Optional[Path]:
        """[9] Strict write discipline: file first, index only on confirmed success."""
        evidence_path = self.session_dir / f"branch_{branch_id}.md"
        with self._write_lock:
            try:
                evidence_path.write_text(content, encoding="utf-8")
                count = content.count("**Finding")
                with open(self.index_path, "a", encoding="utf-8") as f:
                    f.write(f"| {branch_id} | {angle[:40]} "
                            f"| branch_{branch_id}.md | ~{count} | ✅ complete |\n")
                self.index[str(branch_id)] = str(evidence_path)
                log(green(f"  [MEM] Index → branch_{branch_id}.md ({count} findings)"))
                return evidence_path
            except OSError as e:
                log(red(f"  [MEM] ❌ Write failed, index NOT updated: {e}"))
                return None

    def read_branch_evidence(self, branch_id) -> str:
        p = self.session_dir / f"branch_{branch_id}.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def read_index(self) -> str:
        return self.index_path.read_text(encoding="utf-8") if self.index_path.exists() else ""

    def write_alerts(self, alert_text: str):
        """Append a critical alert to ALERTS.md."""
        with self._write_lock:
            alerts_path = self.session_dir / "ALERTS.md"
            try:
                with open(alerts_path, "a", encoding="utf-8") as f:
                    f.write(alert_text + "\n\n")
            except OSError as e:
                log(yellow(f"  [ALERTS] Write failed: {e}"))

    def read_alerts(self) -> str:
        p = self.session_dir / "ALERTS.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""


class BranchCheckpoint:
    """
    Write-ahead log: pending_branches.json written before DFS starts.
    Status updated as each branch completes. Enables resume on crash. [10]
    """

    def __init__(self, session_dir: Path):
        self.path = session_dir / "pending_branches.json"

    def init(self, branches: list[dict]):
        state = {str(b["branch_id"]): "pending" for b in branches}
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def mark_complete(self, branch_id):
        if not self.path.exists():
            return
        state = json.loads(self.path.read_text(encoding="utf-8"))
        state[str(branch_id)] = "complete"
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def mark_partial(self, branch_id):
        if not self.path.exists():
            return
        state = json.loads(self.path.read_text(encoding="utf-8"))
        state[str(branch_id)] = "partial"
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def pending_ids(self) -> list[str]:
        if not self.path.exists():
            return []
        return [k for k, v in json.loads(self.path.read_text()).items()
                if v == "pending"]

    @staticmethod
    def find_resumable(cwd: Path = Path.cwd()) -> Optional[Path]:
        candidates = sorted(cwd.glob("session_*/pending_branches.json"), reverse=True)
        for cp in candidates:
            state = json.loads(cp.read_text(encoding="utf-8"))
            if any(v == "pending" for v in state.values()):
                return cp.parent
        return None


class PipelineCheckpoint:
    """
    Saves and restores pipeline state across stages so a failed/interrupted
    run can be resumed without re-running completed stages.

    Stages in order: bfs → dfs → uu → contradiction → synthesis
    """

    STAGES = ["bfs", "dfs", "uu", "contradiction", "synthesis"]

    def __init__(self, session_dir: Path):
        self.path = session_dir / "pipeline_state.json"
        self.session_dir = session_dir

    def save(self, stage_reached: str, **kwargs):
        """Save state after completing a stage. kwargs become part of the state."""
        existing = self._load_raw()
        state = {**existing, "stage_reached": stage_reached, **kwargs}
        self.path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    def load(self) -> dict:
        return self._load_raw()

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def stage_reached(self) -> str:
        return self._load_raw().get("stage_reached", "")

    def is_complete(self, stage: str) -> bool:
        reached = self.stage_reached()
        if not reached:
            return False
        reached_idx = self.STAGES.index(reached) if reached in self.STAGES else -1
        stage_idx   = self.STAGES.index(stage)   if stage   in self.STAGES else 999
        return reached_idx >= stage_idx

    @staticmethod
    def find_latest(data_dir: Path) -> "PipelineCheckpoint | None":
        """Find the most recent session with a resumable pipeline state."""
        candidates = sorted(data_dir.glob("session_*/pipeline_state.json"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        for cp_path in candidates:
            try:
                state = json.loads(cp_path.read_text())
                # Resumable if didn't reach synthesis
                if state.get("stage_reached") in ("bfs", "dfs", "uu", "contradiction"):
                    return PipelineCheckpoint(cp_path.parent)
            except Exception:
                continue
        return None
