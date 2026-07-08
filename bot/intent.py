"""
bot/intent.py — LLM-based intent classification.

Short messages (≤2 words) are treated as casual without an LLM call.
Everything longer goes to the flash model to decide.
"""

import asyncio

_INTENT_SYSTEM = (
    "You classify messages sent to a medical research bot used by doctors.\n"
    "Reply with exactly one word: 'research' or 'casual'.\n\n"
    "RESEARCH: a genuine clinical question about a patient, drug, disease, "
    "surgery, dosing, guidelines, or diagnosis. Must contain actual medical "
    "content — a condition, drug name, age/sex of patient, procedure, etc.\n\n"
    "CASUAL: anything else — greetings, testing the bot, asking if it works, "
    "meta questions about the bot, vague questions with no clinical content, "
    "small talk, messages without any medical specifics.\n\n"
    "A message is only RESEARCH if it contains real clinical details. "
    "Messages like 'what is this?', 'still a test', 'does it work', "
    "'is this working', 'what can you do' are ALWAYS casual.\n\n"
    "When uncertain, answer 'casual'."
)


def _sync_llm_classify(text: str) -> str:
    from cram.provider.openrouter import llm
    try:
        result = llm(
            [{"role": "user", "content": text}],
            system=_INTENT_SYSTEM,
            phase="intent",
            temperature=0.0,
            label="intent",
        ).strip().lower()
        return "research" if result.startswith("research") else "casual"
    except Exception:
        return "research"  # default to research so real queries aren't dropped


async def classify(text: str) -> str:
    text = text.strip()
    if not text:
        return "casual"

    # Very short messages (1-2 words) are never research queries
    if len(text.split()) <= 2:
        return "casual"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_llm_classify, text)


# ── Casual reply rotation ──────────────────────────────────────────────────────

_CASUAL_REPLIES = [
    "Hi! Send me a clinical scenario and I'll search the literature for you.",
    "Hello! Ready when you are — send me a patient scenario to research.",
    "Hey! Give me a clinical question and I'll get to work.",
    "Hi there! Send me a clinical case or research question to get started.",
]

_reply_index = 0


def casual_reply() -> str:
    global _reply_index
    reply = _CASUAL_REPLIES[_reply_index % len(_CASUAL_REPLIES)]
    _reply_index += 1
    return reply
