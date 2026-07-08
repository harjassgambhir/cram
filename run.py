"""
run.py — Main orchestrator. Ties all pipeline stages together.
This is the only file that knows the full sequence.
Every stage is importable independently for testing.
"""

import queue
import re
import shutil
import sys
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cram.config as _cfg
from cram.config import SYNTHESIS_SYSTEM   # static — safe to bind at import
from cram.log import log, bold, dim, green, yellow, cyan, red, blue, set_corr, print_session_stats, section, error_panel, spin, stats_panel
from cram.memory.persistent import PersistentMemory, scan_for_injection, strip_injection
from cram.config import MAX_SCENARIO_LEN
from cram.memory.session_search import SessionSearch
from cram.memory.store import ResearchMemory, BranchCheckpoint, PipelineCheckpoint
from cram.provider.openrouter import CreditExhaustedError
from cram.pipeline.intake import collect_structured_intake, interrogate_scenario
from cram.pipeline.question_analyzer import analyze_question
from cram.pipeline.bfs import bfs_decompose, plan_phase
from cram.pipeline.dfs import dfs_branch, get_source_status, SOURCE_COUNT
from cram.pipeline.contradiction import detect_contradictions
from cram.pipeline.unknown_unknowns import run_unknown_unknowns
from cram.pipeline.synthesis import synthesize_report
from cram.pipeline.alerts import format_alerts_section
from cram.pipeline.verifier import reset_discarded, get_discarded


def run_research(
    scenario: str,
    output_file: Optional[str] = None,
    auto: bool = False,
    resume_dir: Optional[Path] = None,
    patient_profile: str = "",
    enter_chat: bool = True,
    pdf: bool = False,
    progress_callback=None,
    plan_callback=None,
    n_branches: Optional[int] = None,
    dfs_depth: Optional[int] = None,
) -> str:
    """
    Full research pipeline.
    Returns the completed report as a string.

    progress_callback(stage: str, detail: str, pct: int) — called at key stages.
      stage: short label ("bfs", "branch_done", "synthesis", "done", ...)
      detail: human-readable message
      pct: 0–100 estimated completion

    plan_callback(branches: list, question_analysis: dict) -> list
      If provided, called instead of the interactive plan_phase().
      Must return the (possibly modified) branches list.
      Use this for non-interactive callers (e.g. bots) that handle plan
      confirmation themselves. Runs synchronously (may block).
    """
    try:
        return _run_research_inner(
            scenario=scenario,
            output_file=output_file,
            auto=auto,
            resume_dir=resume_dir,
            patient_profile=patient_profile,
            enter_chat=enter_chat,
            pdf=pdf,
            progress_callback=progress_callback,
            plan_callback=plan_callback,
            n_branches=n_branches,
            dfs_depth=dfs_depth,
        )
    except CreditExhaustedError as e:
        # Find the most recent session dir to show in the message
        try:
            session_dirs = sorted(_cfg.DATA_DIR.glob("session_*"),
                                  key=lambda d: d.stat().st_mtime, reverse=True)
            _sd = str(session_dirs[0]) if session_dirs else str(_cfg.DATA_DIR / "session_<id>")
        except Exception:
            _sd = str(_cfg.DATA_DIR / "session_<id>")
        error_panel(
            "CREDITS EXHAUSTED",
            f"{e}\n\n"
            f"Your session is saved at:\n  {_sd}\n\n"
            f"After adding credits, resume with:\n"
            f"  cram --resume-session {_sd}"
        )
        raise


def _run_research_inner(
    scenario: str,
    output_file: Optional[str] = None,
    auto: bool = False,
    resume_dir: Optional[Path] = None,
    patient_profile: str = "",
    enter_chat: bool = True,
    pdf: bool = False,
    progress_callback=None,
    plan_callback=None,
    n_branches: Optional[int] = None,
    dfs_depth: Optional[int] = None,
) -> str:
    """Inner implementation of run_research (wrapped for CreditExhaustedError handling)."""
    # Per-run overrides (e.g. from bot user settings)
    eff_branches = n_branches or _cfg.BFS_BRANCHES
    eff_depth    = dfs_depth  or _cfg.DFS_DEPTH

    def _progress(stage: str, detail: str, pct: int) -> None:
        if progress_callback:
            try:
                progress_callback(stage, detail, pct)
            except Exception:
                pass
    start = datetime.now()
    ts    = start.strftime("%Y%m%d_%H%M%S")
    set_corr(session_id=ts[:8])

    if len(scenario) > MAX_SCENARIO_LEN:
        log(yellow(f"  ⚠ Scenario is {len(scenario)} chars (max {MAX_SCENARIO_LEN}). Truncating."))
        scenario = scenario[:MAX_SCENARIO_LEN]

    section("CRAM-1 — Clinical Research Agent Model 1")
    log(f"  Model     : {cyan(_cfg.MODEL)}")
    log(f"  Branches  : {eff_branches}  |  DFS depth : {eff_depth}  |  Workers: {_cfg.MAX_WORKERS}")
    log(f"  Data dir  : {_cfg.DATA_DIR}/")
    log(f"  Started   : {start.strftime('%Y-%m-%d %H:%M:%S')}")
    log()
    for line in textwrap.wrap(scenario, 56):
        log(f"  {line}")
    log()

    # ── Reset verifier discard tracker for this session ──────────────────────
    reset_discarded()

    # ── Persistent memory + session search ────────────────────────────────────
    persistent_mem = PersistentMemory(_cfg.DATA_DIR)
    session_search = SessionSearch(_cfg.DATA_DIR)

    past = session_search.search(scenario[:60], limit=3)
    if past:
        log(blue(f"  📂 {len(past)} related past session(s) found:"))
        for p in past:
            log(dim(f"    • {p['date'][:10]}: {p['scenario'][:80]}"))

    # ── Injection check ───────────────────────────────────────────────────────
    injection_match = scan_for_injection(scenario)
    if injection_match:
        log(yellow(f"  ⚠ Potential prompt injection detected in scenario: '{injection_match}'"))
        log(yellow("  Sanitizing scenario input..."))
        scenario, _stripped = strip_injection(scenario)
        if _stripped:
            log(yellow("  ✓ Injection content removed from scenario."))

    # ── Directive §1.1-1.3: scenario interrogation ────────────────────────────
    interrogation_block = interrogate_scenario(scenario)

    # ── Question analysis — understand what the user actually wants ───────────
    question_analysis = analyze_question(scenario)

    # ── Session dir ───────────────────────────────────────────────────────────
    if resume_dir:
        session_dir = resume_dir
        log(yellow(f"  ♻️  Resuming session: {session_dir}/"))
    else:
        session_dir = _cfg.DATA_DIR / f"session_{ts}"
    memory = ResearchMemory(session_dir)
    pipeline_cp = PipelineCheckpoint(session_dir)
    log(blue(f"  [MEM] Session: {session_dir}/"))

    # ── BFS ───────────────────────────────────────────────────────────────────
    _progress("bfs_start", "Decomposing research strategy…", 5)
    branches = bfs_decompose(scenario, n=eff_branches,
                             question_analysis=question_analysis)
    _progress("bfs_done", f"{len(branches)} research branches planned", 10)

    # ── [8] Plan/Build confirmation ───────────────────────────────────────────
    if plan_callback is not None:
        # Non-interactive caller supplies its own plan approval (e.g. bot)
        branches = plan_callback(branches, question_analysis)
    else:
        branches = plan_phase(scenario, branches, auto=auto,
                              question_analysis=question_analysis)
    _progress("plan_confirmed", f"Plan confirmed — {len(branches)} branches", 12)

    # ── [10] Write-ahead log ──────────────────────────────────────────────────
    checkpoint = BranchCheckpoint(session_dir)

    if resume_dir:
        pending = checkpoint.pending_ids()
        if pending:
            orig      = len(branches)
            branches  = [b for b in branches if str(b.get("branch_id")) in pending]
            log(yellow(f"  ♻️  Resuming {len(branches)}/{orig} pending branches"))
        else:
            log(green("  ♻️  All branches complete — skipping to synthesis"))
            branches = []

    if branches:
        checkpoint.init(branches)

    # ── DFS — parallel branches ────────────────────────────────────────────────
    n_parallel = min(_cfg.PARALLEL_BRANCHES, len(branches))
    section("DFS PHASE", subtitle=f"{len(branches)} branches × depth {eff_depth} ({n_parallel} parallel)")
    if not auto and sys.stdin.isatty():
        log(dim("  Tip: Type a question and press Enter to add a new research direction."))

    # D.1: Non-blocking stdin listener — user can queue new branches during research
    _user_q: queue.Queue[str] = queue.Queue()
    _completed_count = [0]
    _completed_lock  = threading.Lock()

    def _stdin_listener():
        while True:
            try:
                line = input()
                if line.strip():
                    _user_q.put(line.strip())
            except EOFError:
                break

    if not auto and sys.stdin.isatty():
        threading.Thread(target=_stdin_listener, daemon=True).start()

    def _run_branch(branch: dict) -> dict:
        # Drain any user-queued branches before starting (best-effort)
        while not _user_q.empty():
            user_q_text = _user_q.get_nowait()
            if user_q_text.lower() == "/status":
                with _completed_lock:
                    done = _completed_count[0]
                log(cyan(f"  Status: {done}/{len(branches)} branches done"))
            else:
                log(cyan(f"  Queuing branch: \"{user_q_text[:80]}\""))
                new_branch = {
                    "branch_id": max((b.get("branch_id", 0) for b in branches), default=0) + 1,
                    "angle":     user_q_text[:80],
                    "rationale": "User-requested during research",
                    "primary_query": user_q_text[:60],
                    "followup_queries": [],
                }
                branches.append(new_branch)
        return dfs_branch(
            branch, scenario, memory,
            patient_profile=patient_profile,
            depth=eff_depth,
            checkpoint=checkpoint,
            question_analysis=question_analysis,
        )

    all_branch_data: list[dict] = []
    with ThreadPoolExecutor(max_workers=n_parallel) as ex:
        submitted: set[int] = set()

        def _submit_pending():
            for b in branches:
                bid = b.get("branch_id")
                if bid not in submitted:
                    submitted.add(bid)
                    fut = ex.submit(_run_branch, b)
                    pending_futures[fut] = b

        pending_futures: dict = {}
        _submit_pending()

        while pending_futures:
            done_futures = []
            for fut in list(pending_futures):
                if fut.done():
                    done_futures.append(fut)

            if not done_futures:
                threading.Event().wait(0.5)
                _submit_pending()
                continue

            for fut in done_futures:
                branch = pending_futures.pop(fut)
                try:
                    bd = fut.result()
                    all_branch_data.append(bd)
                    with _completed_lock:
                        _completed_count[0] += 1
                    done = _completed_count[0]
                    log(green(f"\n  ✅ Branch [{branch.get('branch_id')}] done "
                              f"({done}/{len(branches)} complete)"))
                    branch_pct = 12 + int((done / max(len(branches), 1)) * 60)
                    _progress(
                        "branch_done",
                        f"Branch {done}/{len(branches)} done: {branch.get('angle','')[:60]}",
                        branch_pct,
                    )
                except Exception as e:
                    log(red(f"  ❌ Branch [{branch.get('branch_id')}] failed: {e}"))

            _submit_pending()

    # ── Source health report ─────────────────────────────────────────────────
    src_status = get_source_status()
    if src_status["disabled"]:
        log(yellow(f"  ⚠ Sources disabled this session: {', '.join(src_status['disabled'])}"))

    # ── Save DFS checkpoint ───────────────────────────────────────────────────
    if all_branch_data:
        pipeline_cp.save("dfs",
            scenario=scenario,
            question_analysis=question_analysis,
            interrogation_block=interrogation_block,
            patient_profile=patient_profile,
            branch_ids=[b.get("branch_id") for b in all_branch_data],
            branch_angles={str(b.get("branch_id")): b.get("angle", "") for b in all_branch_data},
        )

    # ── Resume: restore branch data from checkpoint if DFS already complete ───
    if resume_dir and pipeline_cp.is_complete("dfs") and not all_branch_data:
        saved = pipeline_cp.load()
        for bid in saved.get("branch_ids", []):
            angle = saved.get("branch_angles", {}).get(str(bid), "")
            evidence = memory.read_branch_evidence(bid)
            if evidence:
                all_branch_data.append({
                    "branch_id": bid, "angle": angle, "findings": [],
                    "raw_results": [], "consolidated": evidence,
                })
        if all_branch_data:
            log(green(f"  ♻️  Restored {len(all_branch_data)} branches from checkpoint"))

    _progress("dfs_done", "All branches complete — running final analysis", 75)

    # ── [§6] Unknown-Unknown branch ───────────────────────────────────────────
    if all_branch_data:
        uu = run_unknown_unknowns(
            scenario, all_branch_data, memory,
            question_analysis=question_analysis,
            patient_profile=patient_profile,
        )
        if uu.get("findings"):
            all_branch_data.append(uu)

    pipeline_cp.save("uu")

    # ── [12] Contradiction detection ─────────────────────────────────────────
    contradiction_report = ""
    if resume_dir and pipeline_cp.is_complete("contradiction"):
        saved = pipeline_cp.load()
        contradiction_report = saved.get("contradiction_report", "")
        log(green("  ♻️  Restored contradiction report from checkpoint"))
    else:
        contradiction_report = detect_contradictions(all_branch_data) if all_branch_data else ""
        pipeline_cp.save("contradiction", contradiction_report=contradiction_report)

    _progress("synthesis_start", "Synthesising evidence into report…", 82)
    section("SYNTHESIS PHASE")

    # ── Synthesis + combined review ───────────────────────────────────────────
    report, all_raw, safety_section, safety_ready = synthesize_report(
        scenario, all_branch_data, memory, persistent_mem,
        contradiction_report=contradiction_report,
        interrogation_block=interrogation_block,
        patient_profile=patient_profile,
        question_analysis=question_analysis,
    )

    elapsed = int((datetime.now() - start).total_seconds())

    # ── Resolve the report path now so the session index records it ───────────
    if not output_file:
        slug        = re.sub(r"[^\w]", "_", scenario[:40].lower())
        output_file = f"report_{ts}_{slug}.md"

    # ── Index session ─────────────────────────────────────────────────────────
    summary_lines = [
        f"{b['angle']}: {b['findings'][0][:80]}"
        for b in all_branch_data if b.get("findings")
    ]
    session_search.add_session(
        scenario,
        "; ".join(summary_lines[:5]),
        output_file,
        start.isoformat(),
        len(all_raw),
        field="general",
    )

    # ── Save to persistent memory ─────────────────────────────────────────────
    key_topics  = [b["angle"] for b in all_branch_data if b.get("angle")]
    pmids_found = {str(r["pmid"]) for b in all_branch_data
                   for r in b.get("raw_results", []) if r.get("pmid")}
    lesson = (
        f"{scenario[:100]} | "
        f"Topics: {', '.join(key_topics[:3])} | "
        f"PMIDs: {', '.join(sorted(pmids_found)[:5])}"
    )
    persistent_mem.add("memory", lesson, field="general")

    # ── Assemble report ───────────────────────────────────────────────────────
    qtype_label = question_analysis.get("question_type", "unknown") if question_analysis else "auto"
    model_big = _cfg.MODEL_TIER_BIG or _cfg.MODEL
    model_res = _cfg.MODEL_TIER_RESEARCH or _cfg.MODEL
    if model_big == model_res:
        model_line = f"**Model:** {_cfg.MODEL}"
    else:
        model_line = f"**Models:** Planning/Synthesis: {model_big} | Research: {model_res}"

    header = (
        f"# CRAM-1 Clinical Research Brief\n"
        f"**Report Type:** {qtype_label.replace('_', ' ').title()}  \n"
        f"**Generated:** {start.strftime('%B %d, %Y at %H:%M')}  \n"
        f"**Duration:** {elapsed // 60}m {elapsed % 60}s  \n"
        f"{model_line}  \n"
        f"**Architecture:** CRAM-1 | BFS({eff_branches}) → DFS({eff_depth}) | "
        f"{SOURCE_COUNT} sources + full-text enrichment | alerts | contradiction detection | "
        f"unknown-unknowns | combined safety review  \n\n"
        f"> ⚠️ **DISCLAIMER**: AI-assisted literature synthesis for clinical reference only.\n"
        f"> Clinical scenario data is transmitted to the configured LLM provider for processing.\n"
        f"> Does not replace clinical judgment, institutional protocols, or specialist consultation.\n"
        f"> Every claim must be verified against the cited source documents.\n\n"
        f"**Evidence grades:** "
        f"🟢🟢 Cochrane/meta-analysis · "
        f"🟢 RCT · "
        f"🟡🟡 Systematic review/cohort · "
        f"🟡 Cohort study · "
        f"🟠 Case-control · "
        f"🔴 Case series · "
        f"⚫ Expert opinion · "
        f"⚠️ High clinical risk · "
        f"⁇ Suspect/unverifiable citation · "
        f"[UU] Unknown unknown (gap identified by AI)  \n\n"
        f"---\n\n"
    )

    # C.2: Safety gating — if not ready, prepend a prominent banner
    safety_banner = ""
    if not safety_ready:
        safety_banner = (
            "\n> 🚨 **SAFETY REVIEW: NOT READY FOR CLINICAL USE**\n"
            "> The automated safety review identified issues that must be resolved.\n"
            "> See the Safety Review section at the bottom of this report.\n"
            "> Do NOT use this report for clinical decisions until issues are addressed.\n\n"
        )
        log(red("  ⚠️  SAFETY GATE: Report flagged as not ready for clinical use"))

    if interrogation_block:
        header += interrogation_block

    header += f"## Clinical Scenario\n\n> {scenario}\n\n---\n\n"
    if safety_banner:
        header += safety_banner

    # ── Other Directions Explored ─────────────────────────────────────────────
    other_directions = _build_other_directions_section(get_discarded())

    full_report = header + report + other_directions + safety_section

    Path(output_file).write_text(full_report, encoding="utf-8")
    _progress("report_written", f"Report saved: {output_file}", 95)

    # ── PDF export ────────────────────────────────────────────────────────────
    if pdf:
        from cram.pipeline.pdf import markdown_to_pdf
        markdown_to_pdf(output_file)

    _progress("done", output_file, 100)

    # ── Auto-cleanup session dirs > 7 days ────────────────────────────────────
    for d in sorted(_cfg.DATA_DIR.glob("session_*")):
        try:
            if datetime.fromtimestamp(d.stat().st_mtime) < datetime.now() - timedelta(days=7):
                shutil.rmtree(d)
                log(dim(f"  [CLEANUP] Removed: {d.name}"))
        except OSError:
            pass

    # ── Stats ─────────────────────────────────────────────────────────────────
    stats_panel(elapsed)

    section("RESEARCH COMPLETE")
    log(f"  Report    : {green(output_file)}")
    log(f"  Session   : {session_dir}/")
    log(f"  Persistent: {_cfg.DATA_DIR}/")
    log()

    # ── §8.1: Auto-enter chat ─────────────────────────────────────────────────
    if enter_chat:
        from cram.pipeline.chat import session_chat_loop
        _show_chat_intro(all_branch_data, memory)
        session_chat_loop(session_dir, auto_entered=True)

    return full_report


def _build_other_directions_section(discarded: list[dict]) -> str:
    """
    Build a brief 'Other Directions Explored' section from verifier discards.
    Capped at 10 bullets — a quick signpost, not a second report.
    """
    if not discarded:
        return ""

    seen: set[str] = set()
    unique: list[dict] = []
    for d in discarded:
        key = d["finding"][:60]
        if key not in seen:
            seen.add(key)
            unique.append(d)

    items = unique[:10]

    lines = ["\n\n---\n\n## Other Directions Explored\n\n"]
    lines.append(
        "_The following research directions were attempted but did not yield "
        "verifiable evidence sufficient for inclusion in the main report._\n\n"
    )
    for item in items:
        reason = item.get("reason", "insufficient evidence")
        finding = item["finding"]
        if len(finding) > 200:
            finding = finding[:197] + "..."
        lines.append(f"- {finding} _(not included: {reason})_\n")

    return "".join(lines)


def _show_chat_intro(all_branch_data: list[dict], memory: ResearchMemory):
    from cram.log import get_stats
    s = get_stats()
    log()
    log(bold("═" * 60))
    log(bold(f"  Research complete. "
             f"{s['sources_fetched']} sources. "
             f"{len(all_branch_data)} branches. "
             f"{s['alerts_fired']} alerts fired."))
    log(bold("═" * 60))
    log()
    log(cyan("  You can now ask follow-up questions against this evidence:"))
    log(dim('    → "What if we delay surgery 2 weeks?"'))
    log(dim('    → "Summarise the drug interactions for pharmacy"'))
    log(dim('    → "What does anaesthesia need to know?"'))
    log(dim('    → "Is there evidence for cell salvage in this case?"'))
    log()
    log(dim("  Type /quit to exit, /search <query> to run a new targeted search."))
    log()
