"""
log.py — Logging utilities: ANSI colours, correlation IDs, session-level stats.
All other modules import from here; nothing else calls print() directly.
"""

import threading
from contextlib import contextmanager
from typing import Optional

# ── Rich — graceful fallback if not installed ──────────────────────────────────
try:
    from rich.console import Console
    from rich.rule import Rule
    from rich.panel import Panel
    from rich.table import Table
    from rich.status import Status
    _rich = True
except ImportError:
    _rich = False

_console = Console(highlight=False) if _rich else None

# ── Correlation ID (thread-local) ──────────────────────────────────────────────
_corr = threading.local()

def set_corr(session_id: str = "", branch_id: str = "", depth: str = ""):
    _corr.session = session_id
    _corr.branch  = branch_id
    _corr.depth   = depth

def corr_tag() -> str:
    parts = []
    if getattr(_corr, "session", ""): parts.append(_corr.session)
    if getattr(_corr, "branch",  ""): parts.append(f"B{_corr.branch}")
    if getattr(_corr, "depth",   ""): parts.append(f"D{_corr.depth}")
    return f"[{'/'.join(parts)}] " if parts else ""

# ── ANSI helpers ───────────────────────────────────────────────────────────────
def log(msg: str = ""):
    print(msg, flush=True)

def dim(s):     return f"\033[2m{corr_tag()}{s}\033[0m"
def bold(s):    return f"\033[1m{s}\033[0m"
def green(s):   return f"\033[32m{corr_tag()}{s}\033[0m"
def yellow(s):  return f"\033[33m{corr_tag()}{s}\033[0m"
def cyan(s):    return f"\033[36m{s}\033[0m"
def red(s):     return f"\033[31m{corr_tag()}{s}\033[0m"
def blue(s):    return f"\033[34m{corr_tag()}{s}\033[0m"
def magenta(s): return f"\033[35m{s}\033[0m"

# ── Rich-powered TUI helpers ───────────────────────────────────────────────────

def section(title: str, subtitle: str = ""):
    """
    Print a styled section header.
    Rich: horizontal Rule with bold title; plain: box-drawing fallback.
    """
    if _rich and _console is not None:
        _console.print(Rule(title=f"[bold]{title}[/bold]", style="dim"))
        if subtitle:
            _console.print(f"  [dim]{subtitle}[/dim]")
    else:
        width = 60
        log()
        log(bold("╔" + "═" * (width - 2) + "╗"))
        padded = f"  {title}"
        log(bold("║" + padded.ljust(width - 2) + "║"))
        if subtitle:
            sub_padded = f"  {subtitle}"
            log(bold("║" + sub_padded.ljust(width - 2) + "║"))
        log(bold("╚" + "═" * (width - 2) + "╝"))


def error_panel(title: str, body: str):
    """
    Print an error panel.
    Rich: red-bordered Panel; plain: red ANSI lines.
    """
    if _rich and _console is not None:
        _console.print(Panel(body, title=f"[bold red]{title}[/bold red]", border_style="red"))
    else:
        log(red("=" * 60))
        log(red(f"  {title}"))
        log(red("=" * 60))
        for line in body.splitlines():
            log(red(f"  {line}"))
        log(red("=" * 60))


@contextmanager
def spin(label: str):
    """
    Context manager that shows a spinner while work is in progress.
    Rich: animated dots spinner; plain: no-op (yields immediately).
    Thread-safe: only activates on TTY to avoid log corruption in parallel branches.
    """
    import sys
    if _rich and _console is not None and sys.stderr.isatty():
        with _console.status(f"[dim]{label}...[/dim]", spinner="dots"):
            yield
    else:
        yield


def stats_panel(elapsed: int):
    """
    Print session statistics.
    Rich: styled Table; plain: delegates to print_session_stats().
    """
    from cram.provider.openrouter import get_session_cost
    s = get_stats()
    cost_info = get_session_cost()

    if _rich and _console is not None:
        table = Table(title="Session Statistics", show_header=True, header_style="bold cyan",
                      border_style="dim", show_lines=False)
        table.add_column("Metric", style="dim", min_width=22)
        table.add_column("Value", justify="right")

        table.add_row("Duration",          f"{elapsed // 60}m {elapsed % 60}s")
        table.add_row("LLM calls",         str(s["llm_calls"]))
        table.add_row("Prompt tokens",     f"{s['prompt_tokens']:,}")
        table.add_row("Completion tokens", f"{s['completion_tokens']:,}")
        table.add_row("Total tokens",      f"{s['prompt_tokens'] + s['completion_tokens']:,}")
        table.add_row("Est. cost",         f"${cost_info['total_usd']:.4f} USD")
        table.add_row("Retries",           str(s["retries"]))
        table.add_row("Cache hits",        str(s["cache_hits"]))
        table.add_row("Source fetches",    str(s["sources_fetched"]))
        table.add_row("Alerts fired",      str(s["alerts_fired"]))

        for entry in cost_info["breakdown"]:
            table.add_row(
                f"  ↳ {entry['model'][:28]}",
                f"${entry['cost_usd']:.4f}  ({entry['prompt_tokens']:,}+{entry['completion_tokens']:,})",
            )

        _console.print()
        _console.print(table)
    else:
        print_session_stats(elapsed)


# ── Session-level stats accumulator ───────────────────────────────────────────
_session_stats: dict[str, int] = {
    "llm_calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "retries": 0,
    "cache_hits": 0,
    "sources_fetched": 0,
    "alerts_fired": 0,
}
_stats_lock = threading.Lock()

def stat(key: str, n: int = 1):
    with _stats_lock:
        _session_stats[key] = _session_stats.get(key, 0) + n

def get_stats() -> dict:
    with _stats_lock:
        return dict(_session_stats)

def print_session_stats(elapsed: int):
    from cram.provider.openrouter import get_session_cost
    s = get_stats()
    cost_info = get_session_cost()
    log()
    log(bold("╔" + "═" * 58 + "╗"))
    log(bold("║  📊  SESSION STATISTICS" + " " * 35 + "║"))
    log(bold("╚" + "═" * 58 + "╝"))
    log(f"  Duration         : {elapsed // 60}m {elapsed % 60}s")
    log(f"  LLM calls        : {s['llm_calls']}")
    log(f"  Prompt tokens    : {s['prompt_tokens']:,}")
    log(f"  Completion tokens: {s['completion_tokens']:,}")
    log(f"  Total tokens     : {s['prompt_tokens'] + s['completion_tokens']:,}")
    log(f"  Est. cost        : ${cost_info['total_usd']:.4f} USD")
    for entry in cost_info["breakdown"]:
        log(dim(f"    {entry['model']:<30} ${entry['cost_usd']:.4f}  "
                f"({entry['prompt_tokens']:,}+{entry['completion_tokens']:,} tok)"))
    log(f"  Retries          : {s['retries']}")
    log(f"  Cache hits       : {s['cache_hits']}")
    log(f"  Source fetches   : {s['sources_fetched']}")
    log(f"  Alerts fired     : {s['alerts_fired']}")
