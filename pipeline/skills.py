"""
pipeline/skills.py — Progressive specialty skill disclosure [15] and self-authoring [17].

load_specialty_skills(): Inject matching skill files into the prompt before research.
self_author_skills():    Post-session, extract reusable knowledge and write to skill files.
"""

import re as _re
from pathlib import Path
from datetime import datetime

from cram.config import DATA_DIR, SKILLS_SYSTEM, SPECIALTY_KEYWORDS
from cram.provider.openrouter import llm
from cram.log import log, dim, green, yellow, blue


def load_specialty_skills(scenario: str, data_dir: Path = DATA_DIR) -> str:
    """
    [15] Detect specialty from scenario text using config keywords.
    Inject any matching skill .md files found in DATA_DIR/skills/.
    """
    skills_dir = data_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    scenario_lower = scenario.lower()

    matched: list[str] = []
    for specialty, keywords in SPECIALTY_KEYWORDS.items():
        if any(_re.search(r'\b' + _re.escape(kw) + r'\b', scenario_lower) for kw in keywords):
            matched.append(specialty)

    if not matched:
        return ""

    injected: list[str] = []
    for specialty in matched:
        skill_path = skills_dir / f"{specialty}.md"
        if skill_path.exists():
            content = skill_path.read_text(encoding="utf-8").strip()
            injected.append(
                f"\n═══ SPECIALTY SKILL: {specialty.upper()} ═══\n{content}\n"
            )
            log(blue(f"  [SKILL] Loaded: {specialty}.md ({len(content)} chars)"))
        else:
            log(dim(f"  [SKILL] No skill file yet for: {specialty} — will create post-session"))

    return "\n".join(injected)


def self_author_skills(scenario: str, all_branches: list[dict],
                       data_dir: Path = DATA_DIR):
    """
    [17] Post-session: extract reusable knowledge and write/append to
    DATA_DIR/skills/{specialty}.md for future sessions to load.
    Keeps files under 3000 chars by trimming oldest entries.
    Uses the first matched specialty or falls back to 'general'.
    """
    skills_dir = data_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Detect specialty from scenario text
    scenario_lower = scenario.lower()
    matched: list[str] = []
    for sp, keywords in SPECIALTY_KEYWORDS.items():
        if any(_re.search(r'\b' + _re.escape(kw) + r'\b', scenario_lower) for kw in keywords):
            matched.append(sp)
    specialty = matched[0] if matched else "general"

    findings_digest = "\n".join(
        f"Branch [{b['branch_id']}] {b['angle']}: "
        + "; ".join(str(f) for f in b.get("findings", [])[:3])
        for b in all_branches if b.get("findings")
    )

    if not findings_digest.strip():
        return

    prompt = (
        f"Scenario: {scenario}\n\nFindings digest:\n{findings_digest[:3000]}\n\n"
        f"Extract reusable knowledge for future {specialty} research sessions:\n"
        "- PubMed query templates that worked well (4-8 word keyword strings)\n"
        f"- Key complications and risks specific to {specialty}\n"
        "- Specialty-specific sources beyond standard databases\n"
        "- Key PMIDs worth remembering\n"
        "- Clinical pearls from this research\n\n"
        "Format as concise Markdown. Keep under 1500 chars."
    )

    try:
        skill_content = llm(
            [{"role": "user", "content": prompt}],
            system=SKILLS_SYSTEM,
            temperature=0.2,
            label="self-author skill",
            phase="skills",
        )

        timestamp = datetime.now().strftime("%Y-%m-%d")
        entry = (
            f"\n\n---\n"
            f"*Updated: {timestamp} | Scenario: {scenario[:60]}*\n\n"
            f"{skill_content}"
        )

        skill_path = skills_dir / f"{specialty}.md"
        if skill_path.exists():
            existing = skill_path.read_text(encoding="utf-8")
            combined = existing + entry
            # Keep under 3000 chars — trim oldest content from front
            if len(combined) > 3000:
                combined = combined[-3000:]
            skill_path.write_text(combined, encoding="utf-8")
        else:
            skill_path.write_text(
                f"# {specialty.title()} Specialty Skills\n{entry}",
                encoding="utf-8",
            )

        log(green(f"  [SKILL] ✅ Skill file updated: {skill_path.name}"))

    except Exception as e:
        log(yellow(f"  [SKILL] Self-authoring failed ({e})"))
