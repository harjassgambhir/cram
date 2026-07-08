"""
pipeline/chat.py — Interactive Q&A loop against a finished research session.
§8.1: Auto-enter chat after research completes.
§8.2: Chat explicitly says when it can't answer from evidence and offers targeted search.
"""

import textwrap
from pathlib import Path
from typing import Optional

from cram.config import CHAT_SYSTEM
from cram.provider.openrouter import llm
from cram.memory.store import ResearchMemory
from cram.pipeline.compactor import compact
from cram.log import log, bold, dim, green, yellow, red, cyan

# ── prompt_toolkit for slash-command autocomplete (optional) ──────────────────
try:
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.styles import Style as PtStyle
    _PT_AVAILABLE = True
except ImportError:
    _PT_AVAILABLE = False

_CHAT_COMMANDS = [
    "/quit", "/exit", "/q",
    "/clear",
    "/branches",
    "/report",
    "/grep ",
    "/search ",
    "/help",
]

_COMMAND_HELP = {
    "/grep":     "search raw sources for a keyword, PMID, or drug name",
    "/branches": "list all research branches from this session",
    "/report":   "show path to the generated report file",
    "/search":   "run a targeted new search and answer from results",
    "/clear":    "clear conversation history (evidence is retained)",
    "/help":     "show this command list",
    "/quit":     "exit chat",
}


def _chat_input(prompt_text: str, history: Optional[object] = None) -> str:
    """Read user input with autocomplete if prompt_toolkit is available."""
    import sys
    if _PT_AVAILABLE and sys.stdin.isatty():
        completer = WordCompleter(_CHAT_COMMANDS, sentence=True, pattern=None)
        style = PtStyle.from_dict({"": "#00aaff"})
        try:
            return pt_prompt(
                prompt_text,
                completer=completer,
                history=history,
                style=style,
                complete_while_typing=True,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        raise KeyboardInterrupt


# ── Session loading ─────────────────────────────────────────────────────────────

def list_loadable_sessions(cwd: Path = Path.cwd()) -> list[dict]:
    """Find all session dirs with at least one branch file."""
    sessions = []
    for d in sorted(cwd.glob("session_*"), reverse=True):
        branch_files = list(d.glob("branch_*.md"))
        if not branch_files:
            continue
        scenario_hint = ""
        for bf in branch_files[:1]:
            for line in bf.read_text(encoding="utf-8", errors="ignore").split("\n"):
                if "Rationale:" in line:
                    scenario_hint = line.replace("**Rationale:**", "").strip()[:80]
                    break
        parts = d.name.split("_")
        try:
            date_str = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]} {parts[2][:2]}:{parts[2][2:4]}"
        except (IndexError, ValueError):
            date_str = d.name
        total_size  = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        slug        = d.name.replace("session_", "")
        report_files = list(cwd.glob(f"report_{slug}*.md"))
        sessions.append({
            "path":          d,
            "date":          date_str,
            "branch_count":  len(branch_files),
            "scenario_hint": scenario_hint,
            "size_kb":       total_size // 1024,
            "report":        report_files[0] if report_files else None,
            "has_raw":       (d / "raw_results.jsonl").exists(),
        })
    return sessions


def load_session_context(session_dir: Path) -> tuple[str, str]:
    """Load all evidence from a session dir. Returns (context_text, scenario)."""
    parts    = []
    scenario = ""

    # Full report first (richest context)
    cwd  = session_dir.parent
    slug = session_dir.name.replace("session_", "")
    for report_file in cwd.glob(f"report_{slug}*.md"):
        report_content = report_file.read_text(encoding="utf-8", errors="ignore")
        for line in report_content.split("\n"):
            if line.startswith("> ") and "DISCLAIMER" not in line and len(line) > 10:
                scenario = line.lstrip("> ").strip()
                break
        parts.insert(0, f"## Full Research Report\n{report_content[:14000]}")
        break

    # Research index
    index_path = session_dir / "research_index.md"
    if index_path.exists():
        parts.append("## Research Index\n" + index_path.read_text(encoding="utf-8"))

    # Branch evidence files
    for bf in sorted(session_dir.glob("branch_*.md")):
        content = bf.read_text(encoding="utf-8", errors="ignore")
        if not scenario:
            for line in content.split("\n"):
                if "Rationale:" in line:
                    scenario = line.replace("**Rationale:**", "").strip()
                    break
        parts.append(content)

    return "\n\n---\n\n".join(parts), scenario


# ── Chat loop ───────────────────────────────────────────────────────────────────

def session_chat_loop(session_dir: Path, auto_entered: bool = False):
    """
    Interactive Q&A REPL against a loaded research session.
    §8.2: Explicitly tells the user when something can't be answered from evidence.
    """
    import sys
    sys.stdout.write("\033[0m")  # reset any leftover ANSI colour state from research output
    sys.stdout.flush()
    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  💬  SESSION CHAT" + " " * 40 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))

    if auto_entered:
        log(dim("  (Automatically entered after research completed)"))

    log(dim(f"  Loading: {session_dir.name}"))
    context, scenario = load_session_context(session_dir)

    if not context.strip():
        log(red("  ❌ No evidence found in this session dir."))
        return

    branch_count = len(list(session_dir.glob("branch_*.md")))
    has_raw      = (session_dir / "raw_results.jsonl").exists()
    raw_count    = 0
    if has_raw:
        try:
            with open(session_dir / "raw_results.jsonl", encoding="utf-8") as f:
                raw_count = sum(1 for _ in f)
        except OSError:
            pass

    log(green(f"  ✅ Session loaded"))
    log(f"  Scenario  : {scenario[:100] or '(check branch files)' }")
    log(f"  Branches  : {branch_count}")
    log(f"  Raw docs  : {raw_count:,}")
    log(f"  Context   : {len(context):,} chars")
    log()
    log(dim("  Commands: /grep  /branches  /report  /search  /clear  /help  /quit"))
    if _PT_AVAILABLE:
        log(dim("  Tip: Press Tab after / to autocomplete commands."))
    log()
    log(cyan("  Ask any follow-up question about this research."))
    log()

    if len(context) > 18000:
        log(yellow(f"  Context {len(context):,} chars — compacting for chat..."))
        context = compact(context, label="session context", min_chars=18000)
        log(green(f"  Compacted to {len(context):,} chars"))

    session_system = (
        CHAT_SYSTEM
        + "\n\n══════════════════════════════════════════\n"
        + f"LOADED SESSION EVIDENCE ({branch_count} branches, {raw_count} raw sources)\n"
        + "══════════════════════════════════════════\n\n"
        + context
        + "\n\n══════════════════════════════════════════\n"
        + "IMPORTANT: If you cannot answer a question from the above evidence, "
        "say so explicitly: 'This is not covered in the current session evidence.' "
        "Then suggest which search branch or query would find the answer.\n"
        "══════════════════════════════════════════\n"
    )

    memory          = ResearchMemory(session_dir)
    conversation: list[dict] = []
    _history        = InMemoryHistory() if _PT_AVAILABLE else None

    while True:
        try:
            user_input = _chat_input("\n  You: ", history=_history)
        except KeyboardInterrupt:
            log("\n  Session ended.")
            break

        if not user_input:
            continue

        # ── Built-in commands ──────────────────────────────────────────────────
        if user_input.lower() in ("/quit", "/exit", "/q"):
            log("  Session ended.")
            break

        if user_input.lower() == "/clear":
            conversation = []
            log(green("  Conversation history cleared. Evidence retained."))
            continue

        if user_input.lower() in ("/help", "/?"):
            log(bold("  Available commands:"))
            for cmd, desc in _COMMAND_HELP.items():
                log(f"    {cyan(cmd):<18} — {desc}")
            continue

        if user_input.lower() == "/branches":
            for bf in sorted(session_dir.glob("branch_*.md")):
                first = bf.read_text(encoding="utf-8", errors="ignore").split("\n")[0]
                log(f"  {bf.name}: {first.replace('#','').strip()}")
            continue

        if user_input.lower() == "/report":
            slug    = session_dir.name.replace("session_", "")
            reports = list(session_dir.parent.glob(f"report_{slug}*.md"))
            if reports:
                log(f"  Report: {reports[0]}")
            else:
                log(yellow("  No report file found."))
            continue

        if user_input.lower().startswith("/grep "):
            term = user_input[6:].strip()
            hits = memory.grep_raw_results(term)
            if not hits:
                log(yellow(f"  No matches for '{term}'"))
            else:
                log(green(f"  {len(hits)} matches for '{term}':"))
                for h in hits[:8]:
                    log(f"  [{h.get('source','?')}] {h.get('title','')[:80]}")
                    log(dim(f"    {h.get('snippet','')[:120]}"))
            continue

        if user_input.lower().startswith("/search "):
            # §8.2: offer to run targeted search for out-of-scope questions
            query = user_input[8:].strip()
            if not query:
                log(yellow("  Usage: /search <query>"))
                continue
            log(dim(f"  Running targeted search: \"{query}\"..."))
            try:
                from cram.search.pubmed import tool_pubmed
                from cram.search.europe_pmc import tool_europe_pmc
                results = tool_pubmed(query) + tool_europe_pmc(query)
                memory.append_raw_results(results, query)
                snippets = "\n\n".join(
                    f"[{r['source']}] {r.get('title','')}\n{r.get('snippet','')}"
                    for r in results[:6]
                )
                if snippets:
                    answer = llm(
                        [{"role": "user", "content":
                          f"Question: {query}\n\nSearch results:\n{snippets[:3000]}\n\n"
                          "Answer using only these search results. Cite sources."}],
                        system=CHAT_SYSTEM,
                        temperature=0.2,
                        label="targeted search answer",
                        phase="synthesis",
                    )
                    log()
                    log(bold("  Search result:"))
                    for line in answer.split("\n"):
                        for wrapped in textwrap.wrap(line, 72) or [line]:
                            log(f"  {wrapped}")
                else:
                    log(yellow(f"  No results found for: {query}"))
            except Exception as e:
                log(red(f"  Search failed: {e}"))
            continue

        # ── LLM answer ──────────────────────────────────────────────────────────
        conversation.append({"role": "user", "content": user_input})
        log(dim("  Thinking..."))

        try:
            answer = llm(
                conversation,
                system=session_system,
                temperature=0.2,
                label="chat",
                phase="synthesis",
            )
        except Exception as e:
            log(red(f"  Error: {e}"))
            conversation.pop()
            continue

        conversation.append({"role": "assistant", "content": answer})

        log()
        log(bold("  Agent:"))
        for line in answer.split("\n"):
            if line.strip():
                for wrapped in textwrap.wrap(line, width=72) or [line]:
                    log(f"  {wrapped}")
            else:
                log()

        # Warn if history is getting long
        if sum(len(m["content"]) for m in conversation) > 10000:
            log()
            log(yellow("  ⚠  Long conversation. Use /clear if responses slow down."))
