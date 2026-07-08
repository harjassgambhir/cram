"""
cli.py — Command-line interface for CRAM-1.
Entry point: cram  (or: python -m cram)

Default mode: interactive REPL — type a scenario to start research.
One-shot mode: cram -s "clinical scenario"
"""

# ── Load .env BEFORE any cram imports (config.py reads env at import time) ─
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import sys
import json
import textwrap
import argparse
from pathlib import Path

from cram.config import OPENROUTER_API_KEY, DATA_DIR, BFS_BRANCHES, DFS_DEPTH
from cram.log import log, bold, dim, green, yellow, red, cyan


# ── Lazy imports to keep startup fast ─────────────────────────────────────────

def _get_persistent_mem():
    from cram.memory.persistent import PersistentMemory
    return PersistentMemory(DATA_DIR)

def _get_session_search():
    from cram.memory.session_search import SessionSearch
    return SessionSearch(DATA_DIR)

def _get_cache():
    from cram.search.base import get_cache
    return get_cache()


# ── Argparse setup ─────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cram",
        description="CRAM-1 — Clinical Research Agent Model 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        USAGE:
          cram                          Interactive mode (default)
          cram -s "clinical scenario"   One-shot research

        RESEARCH EXAMPLES:
          cram -s "65M portal hypertension planned Whipple, on rivaroxaban"
          cram -s "I want to study diagnostic utility of Xpert Ultra trace results"
          cram -s "Compare pembrolizumab vs nivolumab NSCLC"
          cram -s "..." --auto            Skip plan confirmation
          cram -s "..." --no-chat         Don't enter chat after research
          cram -s "..." -b 4 -d 3         4 branches, depth 3
          cram --resume                   Resume last interrupted session

        QUESTION TYPES (auto-detected from your scenario):
          Pre-op planning     "65M with cirrhosis, planned Whipple..."
          Research design     "I want to study X", "prospective study on..."
          Literature review   "What does evidence say about X?"
          Comparison          "Compare technique A vs B for condition C"
          Case discussion     "Patient presents with X, how to manage?"
          Methodology         "What parameters should I measure for X?"

        INTERACTIVE MODE COMMANDS:
          /help               Show available commands
          /list               Browse past research sessions
          /chat [N]           Load session N into chat (or pick interactively)
          /settings           Show current configuration
          /clear              Clear the screen
          /quit               Exit

        PLAN PHASE COMMANDS (during research):
          Y / Enter           Proceed with research plan
          n                   Abort
          skip N              Remove branch N
          add <topic>         Add a new research direction
          edit N <desc>       Change branch N's focus

        CHAT COMMANDS (after research):
          /branches     — list research branches covered
          /grep <term>  — search raw sources for PMID, drug name, etc.
          /search <q>   — run a targeted new search and answer from it
          /report       — path to the generated report file
          /clear        — reset conversation history (keep evidence)
          /quit         — exit chat (returns to cram prompt)

        MEMORY & SESSIONS:
          cram --memory-list              Show agent memory
          cram --memory-add "text"        Add to memory
          cram --sessions                 List past sessions
          cram --sessions-search "query"  Search past sessions

        CACHE & CLEANUP:
          cram --cache-clear              Clear search cache
          cram --cleanup 14               Delete sessions > 14 days

        MODEL CONFIGURATION (.env):
          OPENROUTER_API_KEY=sk-or-...        Required
          OPENROUTER_MODEL=deepseek/deepseek-v4-flash   Default model

          # Two-tier model architecture:
          MODEL_BIG=deepseek/deepseek-v4-pro        Planning + synthesis
          MODEL_RESEARCH=deepseek/deepseek-v4-flash DFS research execution

          # Per-phase overrides (optional):
          MODEL_BFS=...  MODEL_SYNTHESIS=...  MODEL_VERIFY=...
          MODEL_DFS=...  MODEL_SAFETY=...     MODEL_ALERT=...

        SEARCH API KEYS (all optional):
          EXA_API_KEY=...                     Exa agentic search (exa.ai)
          CORE_API_KEY=...                    CORE open access (core.ac.uk)
          GEMINI_API_KEY=...                  YouTube analysis
          UNPAYWALL_EMAIL=you@example.com     Free full-text access
          NCBI_API_KEY=...                    PubMed rate limit boost
          BRAVE_API_KEY=...                   Brave web search

          CRAM_DATA_DIR=/path/to/storage  Persistent data directory
        """),
    )

    # Research
    parser.add_argument("--scenario", "-s", type=str, default=None,
                        help="Clinical scenario (freeform text)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output report file path")
    parser.add_argument("--branches", "-b", type=int, default=BFS_BRANCHES,
                        help=f"Number of research branches (default: {BFS_BRANCHES})")
    parser.add_argument("--depth", "-d", type=int, default=DFS_DEPTH,
                        help=f"DFS depth per branch (default: {DFS_DEPTH})")
    parser.add_argument("--auto", action="store_true",
                        help="Skip plan confirmation (non-interactive)")
    parser.add_argument("--form", action="store_true",
                        help="Use structured intake form instead of freeform scenario")
    parser.add_argument("--model", "-m", type=str, default=None,
                        help="Override LLM model for all phases")
    parser.add_argument("--pdf", action="store_true",
                        help="Also export report as PDF (requires: pip install markdown weasyprint)")
    parser.add_argument("--no-chat", action="store_true",
                        help="Don't auto-enter chat after research completes")
    parser.add_argument("--resume", action="store_true",
                        help="Resume most recent interrupted session")
    parser.add_argument("--resume-session", type=str, metavar="SESSION_DIR",
                        help="Resume a specific interrupted session by path")

    # Chat
    parser.add_argument("--list", action="store_true",
                        help="List all loadable past sessions")
    parser.add_argument("--chat", type=str, nargs="?", const="PICK",
                        metavar="SESSION_DIR_OR_NUMBER",
                        help="Chat against a past session")

    # Memory
    parser.add_argument("--memory-list",   action="store_true")
    parser.add_argument("--memory-add",    type=str, metavar="TEXT")
    parser.add_argument("--memory-remove", type=str, metavar="TEXT")

    # Sessions
    parser.add_argument("--sessions",        action="store_true",
                        help="List past research sessions")
    parser.add_argument("--sessions-search", type=str, metavar="QUERY")

    # Cache
    parser.add_argument("--cache-clear", action="store_true")
    parser.add_argument("--cache-days",  type=int, default=30,
                        help="With --cache-clear: only entries older than N days")

    # Cleanup
    parser.add_argument("--cleanup",        type=int, default=0, metavar="DAYS")
    parser.add_argument("--cleanup-dry-run",type=int, default=-1, metavar="DAYS")

    return parser


# ── Command handlers ───────────────────────────────────────────────────────────

def handle_memory(args):
    pm = _get_persistent_mem()
    if args.memory_list:
        entries = pm.get_all()
        print("\n═══ AGENT MEMORY ═══")
        for i, e in enumerate(entries.get("memory", []), 1):
            print(f"  {i}. {e[:120]}")
        print("\n═══ PRACTITIONER PROFILE ═══")
        for i, e in enumerate(entries.get("profile", []), 1):
            print(f"  {i}. {e[:120]}")
        return True
    if args.memory_add:
        print(json.dumps(pm.add("memory", args.memory_add), indent=2))
        return True
    if args.memory_remove:
        print(json.dumps(pm.remove("memory", args.memory_remove), indent=2))
        return True
    return False


def handle_sessions(args):
    ss = _get_session_search()
    if args.sessions:
        items = ss.list_sessions()
        if not items:
            print("No past sessions found.")
            return True
        print(f"\n═══ Past Sessions ({len(items)}) ═══")
        for s in items:
            print(f"  {s['date'][:10]} {s['scenario'][:80]} ({s['source_count']} sources)")
        return True
    if args.sessions_search:
        results = ss.search(args.sessions_search)
        if not results:
            print("No matching sessions found.")
            return True
        for r in results:
            print(f"  [{r['date'][:10]}] {r['scenario'][:80]}")
            print(f"    {r['summary'][:200]}")
        return True
    return False


def handle_cache(args):
    if args.cache_clear:
        _get_cache().clear(older_than_days=args.cache_days)
        print(f"Cache cleared (entries older than {args.cache_days} days).")
        return True
    return False


def handle_cleanup(args):
    import shutil
    from datetime import timedelta, datetime

    days    = args.cleanup_dry_run if args.cleanup_dry_run >= 0 else args.cleanup
    dry_run = args.cleanup_dry_run >= 0

    if days <= 0 and not dry_run:
        return False

    cwd       = Path.cwd()
    cutoff    = datetime.now() - timedelta(days=days) if days > 0 else datetime.now()
    to_delete = []
    for d in sorted(cwd.glob("session_*")):
        try:
            mtime = datetime.fromtimestamp(d.stat().st_mtime)
            if mtime < cutoff:
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                to_delete.append((d, mtime, size))
        except OSError:
            continue

    if not to_delete:
        print(f"No session dirs older than {days} day(s).")
        return True

    total = sum(s for _, _, s in to_delete)
    if dry_run:
        print(f"\nDRY RUN — Would delete {len(to_delete)} dirs ({total/1024/1024:.1f} MB)")
        for d, mtime, size in to_delete:
            print(f"  {d.name:40s}  {mtime.strftime('%Y-%m-%d')}  {size/1024:.0f} KB")
    else:
        print(f"\nCleaning {len(to_delete)} dirs ({total/1024/1024:.1f} MB)")
        for d, mtime, size in to_delete:
            shutil.rmtree(d)
            print(f"  🗑️  {d.name}  ({size/1024:.0f} KB)")
    return True


def handle_list(args):
    from cram.pipeline.chat import list_loadable_sessions
    sessions = list_loadable_sessions()
    if not sessions:
        print("\nNo loadable sessions found in current directory.")
        return True
    _print_session_list(sessions)
    print()
    print("  Use: cram --chat <number>  or type /chat <number> in interactive mode")
    return True


def handle_chat(args):
    from cram.pipeline.chat import list_loadable_sessions, session_chat_loop
    sessions = list_loadable_sessions(DATA_DIR)
    if not sessions:
        log(red("❌ No loadable sessions found."))
        return True

    session_dir = _resolve_session(args.chat, sessions)
    if session_dir:
        session_chat_loop(session_dir)
    return True


def _print_session_list(sessions: list[dict]):
    print(f"\n{'═'*60}")
    print(f"  Loadable Sessions ({len(sessions)} found)")
    print(f"{'═'*60}")
    for i, s in enumerate(sessions, 1):
        report_flag = "📄" if s["report"] else "  "
        raw_flag    = "📊" if s["has_raw"] else "  "
        print(f"  [{i:2d}] {report_flag}{raw_flag} {s['date']}  "
              f"{s['branch_count']} branches  {s['size_kb']}KB")
        print(f"        {s['path'].name}")
        if s["scenario_hint"]:
            print(f"        {s['scenario_hint'][:80]}")


def _resolve_session(chat_val: str, sessions: list[dict]) -> "Path | None":
    """Resolve a session number or path string to a Path."""
    if chat_val == "PICK":
        log()
        log(bold("  Pick a session:"))
        for i, s in enumerate(sessions, 1):
            log(f"  [{i:2d}] {s['date']}  {s['branch_count']} branches  {s['path'].name}")
            if s["scenario_hint"]:
                log(dim(f"        {s['scenario_hint'][:80]}"))
        log()
        try:
            chat_val = input("  Enter number or session dir name: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

    try:
        idx = int(chat_val) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]["path"]
        log(red(f"  ❌ Number out of range (1–{len(sessions)})"))
        return None
    except ValueError:
        candidate = Path(chat_val)
        if not candidate.exists():
            candidate = Path.cwd() / chat_val
        if candidate.exists() and candidate.is_dir():
            return candidate
        log(red(f"  ❌ Not found: {chat_val}"))
        return None


# ── Interactive REPL ──────────────────────────────────────────────────────────

def _print_banner():
    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  CRAM-1 — Clinical Research Agent Model 1" + " " * 11 + "║"))
    log(bold("║  17 sources · AI synthesis · safety review" + " " * 14 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))


def _repl_help():
    log()
    log(bold("  Commands:"))
    log(cyan("    /list") + "           Browse past research sessions")
    log(cyan("    /chat [N]") + "       Re-open a past session in chat (N = session number)")
    log(cyan("    /pdf") + "            Toggle PDF export on/off for next research run")
    log(cyan("    /settings") + "       Show current model and config")
    log(cyan("    /clear") + "          Clear the screen")
    log(cyan("    /quit") + "           Exit")
    log()
    log(bold("  Research:"))
    log("    Type any clinical scenario and press Enter to start research.")
    log(dim("    Chat opens automatically when research completes."))
    log(dim("    Type /quit inside chat to return here."))
    log()
    log(bold("  Chat commands (available after research):"))
    log(dim("    /branches  /grep <term>  /search <q>  /report  /clear  /quit"))
    log()
    log(bold("  Examples:"))
    log(dim('    65M cirrhosis planned Whipple on rivaroxaban'))
    log(dim('    Compare pembrolizumab vs nivolumab in NSCLC'))
    log(dim('    I want to study diagnostic utility of Xpert Ultra trace results'))
    log(dim('    Patient presents with acute chest pain, how to manage?'))
    log()


def _repl_settings():
    import cram.config as cfg
    log()
    log(bold("  Current Configuration:"))
    log(f"    Model         : {cyan(cfg.MODEL)}")
    if cfg.MODEL_TIER_BIG:
        log(f"    Planning model: {cyan(cfg.MODEL_TIER_BIG)}")
    if cfg.MODEL_TIER_RESEARCH:
        log(f"    Research model: {cyan(cfg.MODEL_TIER_RESEARCH)}")
    log(f"    Branches      : {cfg.BFS_BRANCHES}")
    log(f"    DFS depth     : {cfg.DFS_DEPTH}")
    log(f"    Workers       : {cfg.MAX_WORKERS}")
    log(f"    Data dir      : {cfg.DATA_DIR}/")
    log()


def _repl_list() -> list[dict]:
    from cram.pipeline.chat import list_loadable_sessions
    sessions = list_loadable_sessions(DATA_DIR)
    if not sessions:
        log(yellow("  No loadable sessions found."))
        return []
    _print_session_list(sessions)
    log()
    return sessions


def _repl_chat(args_str: str, last_session_dir: "Path | None"):
    from cram.pipeline.chat import list_loadable_sessions, session_chat_loop
    sessions = list_loadable_sessions(DATA_DIR)
    if not sessions:
        log(yellow("  No sessions found. Run some research first."))
        return

    if args_str:
        session_dir = _resolve_session(args_str, sessions)
    elif last_session_dir:
        session_dir = last_session_dir
        log(dim(f"  Using last session: {last_session_dir.name}"))
    else:
        session_dir = _resolve_session("PICK", sessions)

    if session_dir:
        session_chat_loop(session_dir)
        log()
        log(dim("  Back in cram. Type a new scenario or /quit to exit."))


def _repl_run_research(scenario: str, args, pdf: bool = False) -> "Path | None":
    """Run research for scenario and return the session dir for later /chat use."""
    from cram.run import run_research
    import cram.config as cfg

    try:
        run_research(
            scenario=scenario,
            output_file=getattr(args, "output", None),
            auto=getattr(args, "auto", False),
            patient_profile="",
            enter_chat=False,   # REPL manages chat separately
            pdf=pdf,
        )
    except KeyboardInterrupt:
        log(yellow("\n  Research interrupted."))

    # Find the most recently created session dir
    try:
        session_dirs = sorted(cfg.DATA_DIR.glob("session_*"),
                              key=lambda d: d.stat().st_mtime, reverse=True)
        return session_dirs[0] if session_dirs else None
    except Exception:
        return None


def _repl(args):
    """
    Interactive REPL — the default mode when cram is run with no arguments.
    Type a clinical scenario to start research.
    Use / commands for navigation and settings.
    """
    _print_banner()
    log()
    log(dim("  Type a clinical scenario to start research, or /help for commands."))
    log(dim("  Tip: Press Tab after / to autocomplete commands."))
    log()

    # Session-level toggles
    _pdf_on = getattr(args, "pdf", False)

    # Prompt_toolkit autocomplete for / commands
    _REPL_COMMANDS = ["/help", "/list", "/chat", "/settings", "/pdf", "/clear", "/quit"]
    _pt_session = None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.styles import Style as PtStyle
        from prompt_toolkit.history import InMemoryHistory
        _repl_completer = WordCompleter(_REPL_COMMANDS, sentence=True, pattern=None)
        _pt_session = PromptSession(
            completer=_repl_completer,
            history=InMemoryHistory(),
            style=PtStyle.from_dict({"": "#00aaff"}),
            complete_while_typing=True,
        )
    except ImportError:
        pass

    def _repl_input(prompt_text: str) -> str:
        if _pt_session and sys.stdin.isatty():
            try:
                return _pt_session.prompt(prompt_text).strip()
            except (EOFError, KeyboardInterrupt):
                raise KeyboardInterrupt
        return input(prompt_text).strip()

    last_session_dir: "Path | None" = None

    def _prompt_text() -> str:
        tag = green(" [pdf]") if _pdf_on else ""
        return bold("cram") + tag + "> "

    while True:
        try:
            line = _repl_input(_prompt_text())
        except (EOFError, KeyboardInterrupt):
            log("\n  Goodbye.")
            break

        if not line:
            continue

        if line.startswith("/"):
            parts = line.split(None, 1)
            cmd      = parts[0].lower()
            args_str = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("/quit", "/exit", "/q"):
                log("  Goodbye.")
                break
            elif cmd == "/help":
                _repl_help()
            elif cmd == "/list":
                _repl_list()
            elif cmd == "/chat":
                _repl_chat(args_str, last_session_dir)
            elif cmd == "/settings":
                _repl_settings()
            elif cmd == "/pdf":
                _pdf_on = not _pdf_on
                log(green(f"  PDF export {'ON' if _pdf_on else 'OFF'} — "
                          f"{'reports will be saved as PDF' if _pdf_on else 'PDF generation disabled'}"))
            elif cmd == "/clear":
                import os
                os.system("clear" if os.name != "nt" else "cls")
                _print_banner()
                log()
            else:
                log(yellow(f"  Unknown command: {cmd}  (type /help)"))
        else:
            # Research run — auto-enter chat when done (same as -s mode)
            last_session_dir = _repl_run_research(line, args, pdf=_pdf_on)
            if last_session_dir:
                from cram.pipeline.chat import session_chat_loop
                import sys
                sys.stdout.write("\033[0m")  # reset any leftover ANSI state
                sys.stdout.flush()
                session_chat_loop(last_session_dir, auto_entered=True)
                log()
                log(dim("  Back at cram prompt. Enter a new scenario or /help."))
            log()


# ── Main entry point ───────────────────────────────────────────────────────────

def main():
    import os
    api_key = os.environ.get("OPENROUTER_API_KEY", "")

    parser = build_parser()
    args   = parser.parse_args()

    # Override globals from args
    import cram.config as cfg
    cfg.BFS_BRANCHES = args.branches
    cfg.DFS_DEPTH    = args.depth

    # ── Informational commands (no API key needed) ────────────────────────────
    if handle_memory(args):  return
    if handle_sessions(args): return
    if handle_cache(args):   return
    if handle_cleanup(args): return
    if args.list:
        handle_list(args)
        return

    # ── Commands that need API key ────────────────────────────────────────────
    if args.chat is not None:
        if not api_key:
            log(red("❌  OPENROUTER_API_KEY not set."))
            sys.exit(1)
        handle_chat(args)
        return

    # ── Require API key for all research operations ───────────────────────────
    if not api_key:
        log(red("❌  OPENROUTER_API_KEY not set. Add to .env or environment."))
        sys.exit(1)

    cfg.OPENROUTER_API_KEY = api_key

    if args.model:
        cfg.MODEL = args.model
        cfg.MODEL_TIER_BIG = args.model
        cfg.MODEL_TIER_RESEARCH = args.model
        for phase in cfg.PROVIDER_CONFIG:
            cfg.PROVIDER_CONFIG[phase] = args.model
        log(dim(f"  Model override (all phases): {args.model}"))

    # ── Resume ────────────────────────────────────────────────────────────────
    resume_dir = None
    if getattr(args, "resume_session", None):
        resume_dir = Path(args.resume_session)
        if resume_dir.exists() and resume_dir.is_dir():
            log(yellow(f"  ♻️  Resuming specific session: {resume_dir}"))
        else:
            log(red(f"  ❌ Session dir not found: {resume_dir}"))
            resume_dir = None
    elif args.resume:
        from cram.memory.store import BranchCheckpoint, PipelineCheckpoint
        # Try PipelineCheckpoint first (credit exhaustion resume), then BranchCheckpoint
        pipeline_cp = PipelineCheckpoint.find_latest(DATA_DIR)
        if pipeline_cp:
            resume_dir = pipeline_cp.session_dir
            log(yellow(f"  ♻️  Found resumable pipeline session: {resume_dir}"))
        else:
            resume_dir = BranchCheckpoint.find_resumable()
            if resume_dir:
                log(yellow(f"  ♻️  Found resumable session: {resume_dir}"))
            else:
                log(yellow("  No resumable session found. Starting fresh."))

    # ── No scenario given → interactive REPL ─────────────────────────────────
    if not args.scenario and not args.form:
        _repl(args)
        return

    # ── Get scenario ──────────────────────────────────────────────────────────
    scenario        = args.scenario
    patient_profile = ""

    if not scenario:
        # --form flag: use structured intake
        from cram.pipeline.intake import collect_structured_intake
        intake_data     = collect_structured_intake()
        scenario        = intake_data["scenario"]
        patient_profile = intake_data.get("procedure", "")

    if not scenario:
        log(red("No scenario provided."))
        sys.exit(1)

    # ── Length validation ─────────────────────────────────────────────────────
    from cram.config import MAX_SCENARIO_LEN
    if len(scenario) > MAX_SCENARIO_LEN:
        log(yellow(f"  ⚠ Scenario is {len(scenario)} chars (max {MAX_SCENARIO_LEN}). Truncating."))
        scenario = scenario[:MAX_SCENARIO_LEN]

    # ── Injection check ───────────────────────────────────────────────────────
    from cram.memory.persistent import scan_for_injection, strip_injection
    injection_match = scan_for_injection(scenario)
    if injection_match:
        log(yellow(f"  ⚠ Potential prompt injection detected: '{injection_match}'"))
        log(yellow("  Sanitizing scenario input..."))
        scenario, _stripped = strip_injection(scenario)
        if _stripped:
            log(yellow("  ✓ Injection content removed from scenario."))

    # ── Run research ──────────────────────────────────────────────────────────
    from cram.run import run_research
    run_research(
        scenario=scenario,
        output_file=args.output,
        auto=args.auto,
        resume_dir=resume_dir,
        patient_profile=patient_profile,
        enter_chat=not args.no_chat,
        pdf=getattr(args, "pdf", False),
    )


if __name__ == "__main__":
    main()
