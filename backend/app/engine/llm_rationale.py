"""LLM rationale generation (spec Part 10).

This is the ONLY module in the engine layer allowed to call an LLM, and even
here it never decides anything: it takes an already-decided, structured
finding (root cause, confidence, recommended action, expected impact) and
turns it into a sentence. Root-cause and priority decisions are made
upstream, deterministically, in root_cause.py / recommendation.py.

Routed through OpenRouter (OpenAI-compatible endpoint) rather than calling
Anthropic directly, since that's the key available for this build - still
Claude under the hood, just via a different gateway. OpenRouter's currently
available slug for this model family is 'anthropic/claude-sonnet-5'.
"""
from __future__ import annotations

import openai

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "anthropic/claude-sonnet-5"
RATIONALE_MAX_TOKENS = 300
SUMMARY_MAX_TOKENS = 400

FALLBACK_RATIONALE = (
    "Rationale unavailable right now — the recommendation itself is still valid; "
    "review the underlying metrics directly."
)
FALLBACK_SUMMARY = (
    "AI brief unavailable right now — review the top-priority recommendations directly in the dashboard."
)


def build_client(api_key: str) -> openai.OpenAI:
    """Construct the OpenRouter client. api_key is passed in explicitly by the
    caller (FastAPI job layer) - this module never reads env vars itself."""
    return openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)


def generate_rationale(
    client: openai.OpenAI,
    campaign_name: str,
    metric: str,
    root_cause_label: str,
    confidence: float,
    recommended_action: str,
    expected_impact_value: float,
    expected_impact_pct: float,
) -> str:
    """Turn one already-decided finding into a 2-4 sentence plain-language
    rationale. Claude is given ONLY the structured values below and is
    explicitly forbidden from introducing new claims or re-diagnosing the cause."""
    system = (
        "You write short, plain-language rationales for marketing-campaign "
        "recommendations. The root cause and recommended action have ALREADY been "
        "decided by a deterministic rules engine before you are called — you must "
        "NOT diagnose, re-evaluate, second-guess, or contradict them. Use ONLY the "
        "numbers and labels given to you in the user message; do not invent metrics, "
        "dates, causes, or context that were not provided. Write 2 to 4 plain "
        "sentences. No bullet points, no headers, no markdown."
    )
    user = (
        f"Campaign: {campaign_name}\n"
        f"Metric affected: {metric}\n"
        f"Root cause (already determined, do not re-diagnose): {root_cause_label}\n"
        f"Confidence in root cause: {confidence:.0%}\n"
        f"Recommended action (already decided): {recommended_action}\n"
        f"Expected impact value: {expected_impact_value:.2f}\n"
        f"Expected impact: {expected_impact_pct:.1f}%\n\n"
        "Write the rationale now, using only the values above."
    )
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=RATIONALE_MAX_TOKENS,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        text = (response.choices[0].message.content or "").strip()
        return text or FALLBACK_RATIONALE
    except Exception:
        # Runs inside an automated pipeline job - an LLM/network failure must
        # degrade gracefully, never crash the run.
        return FALLBACK_RATIONALE


def summarize_top_recommendations(client: openai.OpenAI, recommendations: list[dict]) -> str:
    """Executive-summary paragraph for the 'AI Brief' view. `recommendations`
    is the top N pending rows, already sorted by priority_score by the caller."""
    system = (
        "You write a short executive-summary paragraph for an 'AI Brief' dashboard "
        "view, summarizing the top pending campaign-optimization recommendations. "
        "The list you are given is ALREADY prioritized and already decided by a "
        "rules engine — do not re-rank, re-diagnose root causes, or introduce claims "
        "beyond the provided data. Use ONLY the fields given. Write one short "
        "paragraph, 3 to 6 sentences, no bullet points, no markdown."
    )
    lines = [
        (
            f"{i}. campaign_id={rec.get('campaign_id')}, type={rec.get('type')}, "
            f"expected_impact_value={rec.get('expected_impact_value')}, "
            f"expected_impact_pct={rec.get('expected_impact_pct')}, "
            f"confidence_score={rec.get('confidence_score')}, "
            f"priority_score={rec.get('priority_score')}"
        )
        for i, rec in enumerate(recommendations, start=1)
    ]
    user = "Top pending recommendations, already sorted by priority_score:\n" + "\n".join(lines)
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=SUMMARY_MAX_TOKENS,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        text = (response.choices[0].message.content or "").strip()
        return text or FALLBACK_SUMMARY
    except Exception:
        return FALLBACK_SUMMARY
