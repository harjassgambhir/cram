"""
bot/formatter.py — converts CRAM-1 report markdown into Telegram-safe messages.

Telegram limits: 4096 chars per message, MarkdownV2 has strict escaping rules.
Strategy: send a short summary as text, then the full report as a PDF file.
"""

import re
from pathlib import Path
from typing import Optional


# ── Summary extraction ─────────────────────────────────────────────────────────

# Stop summary before these sections (they're long and better in the PDF)
_SUMMARY_STOP_SECTIONS = [
    "## 1.", "## 2.", "## 3.",
    "## PATIENT", "## MEDICATION", "## RENAL",
    "## CARDIOVASCULAR", "## OTHER DIRECTIONS",
    "## 🛡️", "## CRITICAL ALERTS", "## EVIDENCE GAPS",
]

def extract_summary(report_md: str, max_chars: int = 1200) -> str:
    """
    Extract the lead summary from the report — the bolded Summary paragraph
    and the critical alerts block. Keeps it under max_chars.
    """
    lines = report_md.splitlines()
    summary_lines = []
    in_summary = False
    char_count = 0

    for line in lines:
        # Skip YAML-ish header lines (**, Generated:, Duration:, etc.)
        if line.startswith("**Report Type:**") or line.startswith("**Generated:**") \
                or line.startswith("**Duration:**") or line.startswith("**Models:**") \
                or line.startswith("**Architecture:**"):
            continue
        # Stop at long section headers
        if any(line.startswith(stop) for stop in _SUMMARY_STOP_SECTIONS):
            break
        # Start collecting after the report title (# line)
        if line.startswith("# ") and not in_summary:
            in_summary = True
            continue
        if not in_summary:
            continue

        summary_lines.append(line)
        char_count += len(line) + 1
        if char_count >= max_chars:
            break

    summary = "\n".join(summary_lines).strip()

    # Also append critical alerts if present
    alerts = _extract_critical_alerts(report_md)
    if alerts:
        summary += f"\n\n{alerts}"

    return summary[:max_chars].strip()


def _extract_critical_alerts(report_md: str) -> str:
    """Pull the CRITICAL ALERTS block out of the report."""
    m = re.search(
        r"## CRITICAL ALERTS\s*\n(.*?)(?=\n##|\Z)",
        report_md,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return ""
    block = m.group(1).strip()
    # Trim to 3 alert items max
    items = re.findall(r"\d+\.\s+\*\*.*?(?=\n\d+\.|\Z)", block, re.DOTALL)
    return "🚨 *CRITICAL ALERTS*\n" + "\n".join(items[:3]).strip() if items else ""


# ── Telegram MarkdownV2 escaping ───────────────────────────────────────────────

# Characters that must be escaped in MarkdownV2 (outside code/pre blocks)
_ESCAPE_CHARS = r"\_*[]()~`>#+-=|{}.!"


def escape_md(text: str) -> str:
    """Escape all MarkdownV2 special characters in plain text."""
    for ch in _ESCAPE_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text


def md_to_telegram(text: str) -> str:
    """
    Convert a subset of standard markdown to Telegram MarkdownV2.
    Handles: **bold**, *italic*, `code`, ``` code blocks ```, headers → bold.
    Strips unsupported elements (tables, HTML, complex lists).
    """
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove markdown tables (lines starting with |)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-|: ]+$", "", text, flags=re.MULTILINE)
    # Strip mermaid/code blocks — too complex for Telegram
    text = re.sub(r"```(?:mermaid|json|bash).*?```", "[diagram]", text, flags=re.DOTALL)
    # Preserve code blocks (plain ```)
    code_blocks: dict[str, str] = {}
    def _save_code(m):
        key = f"\x00CODE{len(code_blocks)}\x00"
        code_blocks[key] = f"`{escape_md(m.group(1))}`"
        return key
    text = re.sub(r"`([^`\n]+)`", _save_code, text)

    # Convert headers to bold
    text = re.sub(r"^#{1,6}\s+(.+)$", lambda m: f"*{escape_md(m.group(1))}*", text, flags=re.MULTILINE)
    # Convert **bold**
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"*{escape_md(m.group(1))}*", text)
    # Convert *italic* / _italic_ (not already bold)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", lambda m: f"_{escape_md(m.group(1))}_", text)
    text = re.sub(r"_([^_\n]+)_", lambda m: f"_{escape_md(m.group(1))}_", text)
    # Escape remaining plain text (not inside markers)
    # Simple approach: escape chars that aren't already part of MarkdownV2 syntax
    text = re.sub(r"(?<!\\)([>#+=\-.|{}!])", r"\\\1", text)

    # Restore code blocks
    for key, val in code_blocks.items():
        text = text.replace(key, val)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Message chunking ───────────────────────────────────────────────────────────

def split_chunks(text: str, max_len: int = 4000) -> list[str]:
    """
    Split text into chunks of at most max_len chars, breaking at paragraph
    boundaries where possible.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Find last paragraph break before limit
        cut = text.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()

    return [c for c in chunks if c]


# ── PDF path helper ────────────────────────────────────────────────────────────

def find_pdf_for_session(session_dir: Path) -> Optional[Path]:
    """
    Find the PDF report corresponding to a session dir.
    Reports are saved alongside the session in the CWD or DATA_DIR.
    """
    import cram.config as cfg

    session_ts = session_dir.name.replace("session_", "")  # e.g. 20260528_053853

    # Check both DATA_DIR and common working dirs
    search_dirs = [cfg.DATA_DIR, Path.cwd()]
    for d in search_dirs:
        matches = list(d.glob(f"report_{session_ts}*.pdf"))
        if matches:
            return matches[0]
    return None


def find_report_md_for_session(session_dir: Path) -> Optional[Path]:
    """Find the markdown report for a session."""
    import cram.config as cfg

    session_ts = session_dir.name.replace("session_", "")
    for d in [cfg.DATA_DIR, Path.cwd()]:
        matches = list(d.glob(f"report_{session_ts}*.md"))
        if matches:
            return matches[0]
    return None
