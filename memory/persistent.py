"""
memory/persistent.py — Cross-session persistent memory (Hermes Agent pattern).
- MEMORY.md     : agent notes (2200 char limit)
- {FIELD}.md    : field-specific practitioner profile (1375 char limit)
- Auto-consolidation when limit is hit [13]
- Injection scanning [3]
"""

import re
from pathlib import Path
from typing import Optional

import cram.config as _cfg
from cram.config import (
    DATA_DIR, MEMORY_CHAR_LIMIT, PROFILE_CHAR_LIMIT,
    INJECTION_PATTERNS
)
from cram.log import log, dim, green, yellow, red


def scan_for_injection(text: str) -> Optional[str]:
    """Security scan: reject memory entries matching injection patterns."""
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return f"Blocked: matches injection pattern '{pattern}'"
    # Allow common typographic punctuation (em-dash, en-dash, ellipsis, quotes, etc.)
    _ALLOWED_UNICODE = {
        "\u2013",  # en-dash –
        "\u2014",  # em-dash —
        "\u2018",  # left single quote '
        "\u2019",  # right single quote '
        "\u201c",  # left double quote "
        "\u201d",  # right double quote "
        "\u2026",  # ellipsis …
        "\u00b0",  # degree °
        "\u00b5",  # micro µ
        "\u03b1", "\u03b2", "\u03b3",  # Greek letters α β γ (medical)
        "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff",  # format chars
    }
    for ch in text:
        if ord(ch) >= 0x2000 and ch not in _ALLOWED_UNICODE:
            if ord(ch) in range(0x2000, 0x206F):
                return f"Blocked: invisible Unicode U+{ord(ch):04X}"
    return None


def strip_injection(text: str) -> tuple[str, bool]:
    """
    Neutralise prompt-injection content in user input.

    scan_for_injection() only *detects* (returns a human-readable message), so it
    cannot be used as a regex to remove anything. This actually strips the offending
    patterns and invisible control characters, returning (clean_text, was_modified).
    """
    original = text
    for pattern in INJECTION_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    # Drop suspicious invisible Unicode (the same range scan_for_injection flags)
    text = "".join(
        ch for ch in text
        if not (0x2000 <= ord(ch) < 0x206F and ch not in {
            "–", "—", "‘", "’", "“", "”",
            "…", "​", "‌", "‍", "⁠",
        })
    )
    text = text.strip()
    return text, (text != original)


class PersistentMemory:
    """
    Cross-session persistent memory.
    MEMORY.md       — agent notes (MEMORY_CHAR_LIMIT)
    {field}.md      — practitioner profile per field (PROFILE_CHAR_LIMIT)
    [13] Auto-consolidation via LLM compaction before add.
    """

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            data_dir = _cfg.DATA_DIR
        self.data_dir    = data_dir
        self.memory_path = data_dir / "MEMORY.md"
        self._init_files()

    def _init_files(self):
        if not self.memory_path.exists():
            self.memory_path.write_text(
                "# Agent Memory (MEMORY.md)\n# §-separated, max 2200 chars\n\n",
                encoding="utf-8"
            )

    def _profile_path(self, field: str) -> Path:
        return self.data_dir / f"PROFILE_{field.upper()}.md"

    def _ensure_profile(self, field: str) -> Path:
        p = self._profile_path(field)
        if not p.exists():
            p.write_text(
                f"# {field.title()} Practitioner Profile\n# §-separated, max {PROFILE_CHAR_LIMIT} chars\n\n",
                encoding="utf-8"
            )
        return p

    def _read_entries(self, path: Path) -> list[str]:
        content = path.read_text(encoding="utf-8").strip()
        lines   = content.split("\n")
        body_start = 0
        for i, line in enumerate(lines):
            if line.startswith("#"):
                body_start = i + 1
            else:
                break
        body = "\n".join(lines[body_start:]).strip()
        return [e.strip() for e in body.split("§") if e.strip()] if body else []

    def _write_entries(self, path: Path, entries: list[str]):
        header_lines = [l for l in path.read_text(encoding="utf-8").split("\n")
                        if l.startswith("#")] if path.exists() else []
        content = "\n".join(header_lines) + "\n\n" + "§\n".join(entries) + "\n"
        path.write_text(content, encoding="utf-8")

    def _total_chars(self, entries: list[str]) -> int:
        return sum(len(e) for e in entries)

    def _consolidate(self, entries: list[str], limit: int) -> list[str]:
        """[13] Auto-consolidation via LLM compaction."""
        # Import here to avoid circular imports
        from cram.provider.openrouter import llm
        joined = "§\n".join(entries)
        log(dim("  [MEM] Auto-consolidating memory to make room..."))
        try:
            compacted = llm(
                [{"role": "user", "content":
                  f"Compress these memory entries into fewer, denser entries. "
                  f"Preserve all specific facts, PMIDs, lessons. "
                  f"Keep total under {int(limit * 0.8)} chars. "
                  f"Separate entries with §\n\n{joined}"}],
                system="You compress agent memory entries. Be concise but lossless on facts.",
                temperature=0.1,
                label="mem-consolidate",
                phase="compact",
            )
            new_entries = [e.strip() for e in compacted.split("§") if e.strip()]
            if self._total_chars(new_entries) < limit:
                log(green(f"  [MEM] Consolidation: {len(entries)} → {len(new_entries)} entries"))
                return new_entries
        except Exception as e:
            log(yellow(f"  [MEM] Consolidation failed ({e})"))
        return entries

    def add(self, target: str, content: str, field: str = "surgery") -> dict:
        if target == "profile":
            path  = self._ensure_profile(field)
            limit = PROFILE_CHAR_LIMIT
        else:
            path  = self.memory_path
            limit = MEMORY_CHAR_LIMIT

        violation = scan_for_injection(content)
        if violation:
            return {"success": False, "error": violation}

        entries = self._read_entries(path)
        if content in entries:
            return {"success": True, "message": "Already exists"}

        if self._total_chars(entries) + len(content) > limit:
            entries = self._consolidate(entries, limit)
            if self._total_chars(entries) + len(content) > limit:
                return {"success": False,
                        "error": f"Memory full even after consolidation "
                                 f"({self._total_chars(entries)}/{limit})"}

        entries.append(content)
        self._write_entries(path, entries)
        return {"success": True, "usage": f"{self._total_chars(entries)}/{limit}"}

    def replace(self, target: str, old_text: str, content: str, field: str = "surgery") -> dict:
        path  = self._ensure_profile(field) if target == "profile" else self.memory_path
        limit = PROFILE_CHAR_LIMIT if target == "profile" else MEMORY_CHAR_LIMIT
        violation = scan_for_injection(content)
        if violation:
            return {"success": False, "error": violation}
        entries = self._read_entries(path)
        matched = [i for i, e in enumerate(entries) if old_text in e]
        if len(matched) == 0:
            return {"success": False, "error": f"No entry matches '{old_text}'"}
        if len(matched) > 1:
            return {"success": False, "error": "Multiple matches — use a more specific substring"}
        entries[matched[0]] = content
        if self._total_chars(entries) > limit:
            return {"success": False, "error": "Replacement exceeds limit"}
        self._write_entries(path, entries)
        return {"success": True, "usage": f"{self._total_chars(entries)}/{limit}"}

    def remove(self, target: str, old_text: str, field: str = "surgery") -> dict:
        path    = self._ensure_profile(field) if target == "profile" else self.memory_path
        limit   = PROFILE_CHAR_LIMIT if target == "profile" else MEMORY_CHAR_LIMIT
        entries = self._read_entries(path)
        matched = [i for i, e in enumerate(entries) if old_text in e]
        if len(matched) == 0:
            return {"success": False, "error": f"No entry matches '{old_text}'"}
        if len(matched) > 1:
            return {"success": False, "error": "Multiple matches — be more specific"}
        entries.pop(matched[0])
        self._write_entries(path, entries)
        return {"success": True, "usage": f"{self._total_chars(entries)}/{limit}"}

    def get_all(self, field: str = "surgery") -> dict[str, list[str]]:
        profile_path = self._profile_path(field)
        return {
            "memory":  self._read_entries(self.memory_path),
            "profile": self._read_entries(profile_path) if profile_path.exists() else [],
        }

    def format_for_prompt(self, field: str = "surgery") -> str:
        m = self._read_entries(self.memory_path)
        profile_path = self._profile_path(field)
        p = self._read_entries(profile_path) if profile_path.exists() else []
        block = ""
        if m:
            mc    = sum(len(e) for e in m)
            block += f"\n═══ AGENT MEMORY [{int(mc/MEMORY_CHAR_LIMIT*100)}%] ═══\n"
            block += "§\n".join(m) + "\n"
        if p:
            pc    = sum(len(e) for e in p)
            block += f"\n═══ {field.upper()} PROFILE [{int(pc/PROFILE_CHAR_LIMIT*100)}%] ═══\n"
            block += "§\n".join(p) + "\n"
        return block
