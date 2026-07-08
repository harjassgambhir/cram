"""
provider/openrouter.py — Provider abstraction layer.
- llm()      : single call with retry, token tracking, phase-based model selection
- llm_json() : llm() + JSON parse + fallback extraction
- with_retry(): exponential backoff wrapper for any callable
"""

import re
import json
import time
import threading
import requests
from typing import Optional


class CreditExhaustedError(Exception):
    """Raised when OpenRouter returns HTTP 402 and no viable fallback exists."""
    pass

class ModelForbiddenError(Exception):
    """Raised when OpenRouter returns HTTP 403 — model not accessible on this key/plan."""
    pass

from cram.config import (
    OPENROUTER_API_KEY, BASE_URL, PROVIDER_CONFIG, MODEL
)
import cram.config as _cfg   # for FALLBACK_MODEL — use module ref so tests can patch
from cram.log import log, dim, green, yellow, stat

# ── [6] Retry with exponential backoff ────────────────────────────────────────

def with_retry(fn, max_retries: int = 3, base_delay: float = 2.0,
               label: str = "", retryable_codes=(429, 500, 502, 503, 504),
               non_retryable_codes=(402,)):
    """
    Wrap any callable with exponential backoff retry.
    ProxyError (domain blocked/forbidden) is NOT retried — it's permanent.
    ConnectionError from a proxy 403 is also treated as permanent.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in non_retryable_codes:
                raise  # never retry 402 — credits exhausted
            if status not in retryable_codes or attempt == max_retries:
                raise
            last_exc = e
        except requests.exceptions.ProxyError:
            # Proxy block is permanent — no point retrying
            raise
        except requests.exceptions.ConnectionError as e:
            # If it's a proxy tunnel failure, don't retry
            msg = str(e).lower()
            if "tunnel connection failed" in msg or "proxy" in msg:
                raise
            if attempt == max_retries:
                raise
            last_exc = e
        except requests.exceptions.Timeout as e:
            if attempt == max_retries:
                raise
            last_exc = e

        delay = base_delay * (2 ** attempt)
        stat("retries")
        log(yellow(f"  [RETRY] {label} attempt {attempt+1}/{max_retries} "
                   f"failed ({last_exc}), retrying in {delay:.1f}s..."))
        time.sleep(delay)
    raise last_exc   # type: ignore[misc]


# ── Cost tracking — per-model token accumulation ─────────────────────────────

# Pricing per 1M tokens (input, output) in USD — approximate OpenRouter rates
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "anthropic/claude-opus-4-6":       (15.00, 75.00),
    "anthropic/claude-opus-4-5":       (15.00, 75.00),
    "anthropic/claude-sonnet-4-6":     (3.00,  15.00),
    "anthropic/claude-sonnet-4-5":     (3.00,  15.00),
    "anthropic/claude-haiku-4-5":      (0.80,  4.00),
    "minimax/minimax-m2.7":            (0.30,  1.10),
    "thudm/glm-4-32b":                 (0.14,  0.14),
    "qwen/qwen3-235b-a22b":            (0.22,  0.88),
    "google/gemini-2.0-flash-001":     (0.10,  0.40),
    "deepseek/deepseek-v4-pro":        (0.27,  1.10),
    "deepseek/deepseek-v4-flash":      (0.04,  0.16),
}
_DEFAULT_PRICE = (0.50, 1.50)  # fallback if model not in table

_model_token_usage: dict[str, list[int]] = {}  # model → [prompt_tokens, completion_tokens]
_cost_lock = threading.Lock()


def _track_model_cost(model: str, prompt_tokens: int, completion_tokens: int):
    with _cost_lock:
        if model not in _model_token_usage:
            _model_token_usage[model] = [0, 0]
        _model_token_usage[model][0] += prompt_tokens
        _model_token_usage[model][1] += completion_tokens


def get_session_cost() -> dict:
    """Return cost breakdown and total estimated USD for this session."""
    with _cost_lock:
        breakdown = []
        total_usd = 0.0
        for model, (pt, ct) in _model_token_usage.items():
            p_per_m, c_per_m = _MODEL_PRICING.get(model, _DEFAULT_PRICE)
            cost = (pt / 1_000_000) * p_per_m + (ct / 1_000_000) * c_per_m
            total_usd += cost
            breakdown.append({
                "model": model.split("/")[-1],
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "cost_usd": round(cost, 4),
            })
        breakdown.sort(key=lambda x: x["cost_usd"], reverse=True)
        return {"total_usd": round(total_usd, 4), "breakdown": breakdown}


# ── [14] LLM call with provider abstraction ───────────────────────────────────

_llm_call_count = 0
_llm_call_lock  = threading.Lock()

# ── Per-thread overrides (used by bot for per-user API keys / models) ─────────
_thread_local = threading.local()

# Phases that use the "big" (planning/synthesis) model tier
_BIG_PHASES = frozenset({
    "bfs", "synthesis", "safety", "correction", "plan",
    "risk_tier", "uu", "contradiction", "intake", "question_analysis",
})

def set_thread_overrides(
    api_key: Optional[str] = None,
    model_big: Optional[str] = None,
    model_small: Optional[str] = None,
) -> None:
    """Set per-thread LLM overrides. Call from the research thread before run_research()."""
    _thread_local.api_key    = api_key or None
    _thread_local.model_big  = model_big or None
    _thread_local.model_small = model_small or None

def clear_thread_overrides() -> None:
    _thread_local.api_key     = None
    _thread_local.model_big   = None
    _thread_local.model_small = None


def llm(messages: list[dict], system: str = "", temperature: float = 0.3,
        label: str = "", phase: str = "") -> str:
    """
    Provider-abstracted LLM call.
    Selects model by phase, falls back to FALLBACK_MODEL on 429.
    Accumulates tokens into session stats.
    Thread-local overrides (api_key, model_big, model_small) take precedence.
    """
    global _llm_call_count
    with _llm_call_lock:
        _llm_call_count += 1
        n = _llm_call_count

    # Thread-local model overrides (per-user bot settings)
    tl_big   = getattr(_thread_local, "model_big",  None)
    tl_small = getattr(_thread_local, "model_small", None)
    if tl_big or tl_small:
        if phase in _BIG_PHASES and tl_big:
            use_model = tl_big
        elif phase not in _BIG_PHASES and tl_small:
            use_model = tl_small
        else:
            use_model = PROVIDER_CONFIG.get(phase, MODEL) if phase else MODEL
    else:
        use_model = PROVIDER_CONFIG.get(phase, MODEL) if phase else MODEL

    # Thread-local API key override (per-user key)
    api_key = getattr(_thread_local, "api_key", None) or OPENROUTER_API_KEY

    tag = f" [{label}]" if label else ""
    log(dim(f"  ┌─ LLM #{n}{tag} model={use_model.split('/')[-1]}"))
    log(dim(f"  │  → \"{messages[-1]['content'][:100].replace(chr(10),' ')}...\""))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://cram-agent.local",
        "X-Title":       "CRAM-1",
    }

    def _call(model: str) -> str:
        payload = {
            "model":       model,
            "temperature": temperature,
            "messages":    ([{"role": "system", "content": system}] + messages) if system else messages,
        }
        t0   = time.time()
        resp = requests.post(BASE_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data    = resp.json()
        elapsed = time.time() - t0
        usage   = data.get("usage", {})
        pt = usage.get("prompt_tokens", 0) or 0
        ct = usage.get("completion_tokens", 0) or 0
        stat("prompt_tokens", pt)
        stat("completion_tokens", ct)
        stat("llm_calls")
        _track_model_cost(model, pt, ct)
        content = (data["choices"][0]["message"]["content"] or "").strip()
        log(dim(f"  └─ ✓ {elapsed:.1f}s | {pt}→{ct} tok | {len(content)} chars"))
        return content

    try:
        return with_retry(lambda: _call(use_model), label=f"LLM {label}")
    except requests.exceptions.HTTPError as e:
        fallback = _cfg.FALLBACK_MODEL or MODEL
        status = e.response.status_code if e.response is not None else 0
        # Fall back on rate-limit (429) OR payment/access issues for specific model (402, 403)
        if fallback and fallback != use_model and status in (402, 403, 429):
            log(yellow(f"  [PROVIDER] {status} on {use_model.split('/')[-1]} — falling back to {fallback.split('/')[-1]}"))
            try:
                return with_retry(lambda: _call(fallback), label=f"LLM fallback {label}")
            except requests.exceptions.HTTPError as e2:
                fallback_status = e2.response.status_code if e2.response is not None else 0
                if status == 402 and fallback_status == 402:
                    raise CreditExhaustedError(
                        "OpenRouter credits exhausted (HTTP 402).\n"
                        "Add credits at: https://openrouter.ai/credits\n"
                        "Then resume this session with: cram --resume-session SESSION_DIR"
                    ) from e2
                if fallback_status == 403:
                    raise ModelForbiddenError(
                        f"Model '{fallback}' also returned 403 Forbidden.\n"
                        "Neither the primary nor fallback model is accessible.\n"
                        "Check your OpenRouter account or change models in Settings."
                    ) from e2
                raise
        if status == 402:
            raise CreditExhaustedError(
                "OpenRouter credits exhausted (HTTP 402).\n"
                "Add credits at: https://openrouter.ai/credits\n"
                "Then resume this session with: cram --resume-session SESSION_DIR"
            ) from e
        if status == 403:
            raise ModelForbiddenError(
                f"Model '{use_model}' returned 403 Forbidden.\n"
                "The model may not be available on your API key or plan.\n"
                "Try a different model in Settings, or check your OpenRouter account."
            ) from e
        raise


def llm_json(messages: list[dict], system: str = "", label: str = "",
             phase: str = "", temperature: float = 0.3) -> dict | list:
    """llm() + JSON parse with fence stripping and regex fallback."""
    raw   = llm(messages, system=system, label=label, phase=phase, temperature=temperature)
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        # "Extra data" means valid JSON followed by trailing text — decode just the first object
        if "Extra data" in str(exc) and exc.pos:
            try:
                return json.loads(clean[:exc.pos])
            except json.JSONDecodeError:
                pass
        # Fallback: find first complete JSON object/array via decoder
        decoder = json.JSONDecoder()
        for i, ch in enumerate(clean):
            if ch in ("{", "["):
                try:
                    obj, _ = decoder.raw_decode(clean, i)
                    return obj
                except json.JSONDecodeError:
                    continue
        log(yellow(f"  ⚠  JSON parse failed:\n{dim(raw[:400])}"))
        raise
