"""
pipeline/compactor.py — LLM-based context compaction.
Keeps evidence dense but complete when approaching context limits.
"""

import time
from cram.config import COMPACTOR_SYSTEM, RATE_LIMIT_SLEEP
from cram.provider.openrouter import llm
from cram.log import log, dim, green, yellow


def compact(text: str, label: str = "", min_chars: int = 2000) -> str:
    """
    Compress text if it exceeds min_chars.
    Preserves PMIDs, DOIs, specific numbers, safety flags.
    Returns original if already under threshold.
    """
    if len(text) <= min_chars:
        return text

    log(dim(f"  [COMPACT] {len(text):,} chars → compacting [{label}]..."))
    time.sleep(RATE_LIMIT_SLEEP)

    try:
        compacted = llm(
            [{"role": "user", "content": f"Compress this clinical evidence:\n\n{text}"}],
            system=COMPACTOR_SYSTEM,
            temperature=0.1,
            label=f"compact {label}",
            phase="compact",
        )
        log(green(f"  [COMPACT] {len(text):,} → {len(compacted):,} chars"))
        return compacted
    except Exception as e:
        log(yellow(f"  [COMPACT] Failed ({e}) — using original"))
        return text
