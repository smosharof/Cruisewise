"""
Synthesizer sub-agent — runs once per Match flow after the ship_researcher fan-out.

Receives the top-3 ranked ShipAssessments and the original intake; produces the
top_pick_reasoning (why #1 beats #2 and #3 for THIS user) and the counter_memo
(genuine disappointment risk, not a hedge).
"""

from __future__ import annotations

import json
import logging

from agents import Agent, Runner
from pydantic import BaseModel, Field

from backend.agents.subagents.ship_researcher import _humanize_intake
from backend.config import get_settings
from backend.llm import get_chat_model
from backend.schemas import MatchIntake, ShipAssessment

logger = logging.getLogger(__name__)


class SynthesisOutput(BaseModel):
    """Public output of synthesize_memo — bounded to MatchResult's caps.

    These caps are the safety net. The sentence ceilings in the system prompt
    are the primary control. When the model overshoots (long sentences), the
    code-level truncation fallback below cuts at a sentence boundary so this
    contract is always honored.
    """

    top_pick_reasoning: str = Field(
        max_length=600,
        description="Why ranked_candidates[0] beats [1] and [2] for THIS user's intake",
    )
    counter_memo: str = Field(
        max_length=350,
        description="Genuine disappointment risk for the top pick — builds trust",
    )


class _SynthesisAgentOutput(BaseModel):
    """Internal agent output — no char caps so Gemini's structured-output
    validator never rejects a verbose response. We truncate to the public
    SynthesisOutput caps after the agent returns."""

    top_pick_reasoning: str
    counter_memo: str


_TOP_PICK_TRUNC = 580
_COUNTER_MEMO_TRUNC = 340


def _truncate_to_char_limit(text: str, limit: int) -> str:
    """Truncate to the last complete sentence that fits within limit chars.

    Cuts at sentence boundary ('. ') to avoid mid-sentence truncation.
    If no sentence boundary is found in the second half, hard-cuts with ellipsis.
    """
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    last_period = truncated.rfind(". ")
    if last_period > limit // 2:
        return truncated[: last_period + 1]
    return truncated[: limit - 1] + "…"


_SYSTEM_PROMPT = """\
You are a cruise advisor writing a brief comparison memo for ONE specific traveler.

You will receive a JSON object with:
  - intake: the traveler's stated preferences
  - ranked_candidates: the top 3 ShipAssessments, already sorted by vibe_score descending

Output length limits — sentence ceilings are the primary control:
- top_pick_reasoning: maximum 4 sentences. Do not exceed 4 sentences under any
  circumstance. Name the #1 ship, explain why it beats the runners-up for THIS
  user's specific vibe and budget. Reference the user's primary_vibe, party_size,
  and budget_per_person_usd by value.
- counter_memo: maximum 2 sentences. Name one genuine disappointment risk specific
  to this ship and this user. Do not soften it.

Your output is a SynthesisOutput with two fields:

WRITING STYLE (applies to both fields)
  Never use underscore field names (party_size, primary_vibe,
  budget_per_person_usd, travel_party, cruise_experience_level,
  preferred_regions, ranked_candidates, ship_name) in your output.
  Use natural language only. The intake has already been provided to you in
  natural-language fields (who, vibe, budget, regions, duration, experience);
  quote those values directly.

TOP_PICK_REASONING
  Explain why the top-ranked sailing beats the runners-up for THIS traveler.
  Rules:
  - MUST contrast the top pick against #2 and #3 by name (e.g. "Caribbean
    Princess" — natural language, not ranked_candidates[0])
  - Generic praise is rejected. Every sentence must be defensible.
  - One paragraph. No headers, no bullets.
  - If intake.preferred_lines is a list (not "No preference") and the top
    pick is on one of those lines, mention the loyalty match naturally as a
    tiebreaker reason. Do NOT mention the preference if the top pick isn't
    on a preferred line.
  - If intake.relaxed_search is true, the user originally had a tighter
    budget (intake.original_budget_label). Acknowledge in one short sentence
    that prices here exceed that original budget but the preferred-line
    constraint is the reason. Do not pretend the relaxed budget is the
    user's actual cap.

COUNTER_MEMO
  Name the genuine disappointment risk for the top pick. Rules:
  - This is NOT a hedge or a disclaimer. It is a real, named risk specific to this ship.
  - One concrete tradeoff, not a list.
  - Example shape: "If you're hoping for X, Carnival Celebration leans Y; you'd find
    more X on Princess or Holland America."
  - FORBIDDEN: "no cruise is perfect", "always check reviews", "your mileage may vary"
  - The memo should make the traveler trust you MORE because you named a real tradeoff.
"""


async def synthesize_memo(
    intake: MatchIntake, ranked: list[ShipAssessment]
) -> SynthesisOutput:
    """Synthesise top_pick_reasoning + counter_memo from the top 3 candidates.

    Caller must pass ranked sorted by vibe_score descending. Trims to top 3
    before sending; if fewer than 3 are present, uses what's available.
    """
    if not ranked:
        raise ValueError("synthesize_memo requires at least one ranked candidate")

    settings = get_settings()
    top_three = ranked[:3]

    user_message = json.dumps(
        {
            "intake": _humanize_intake(intake),
            "ranked_candidates": [a.model_dump(mode="json") for a in top_three],
        },
        indent=2,
    )

    agent = Agent(
        name="synthesizer",
        instructions=_SYSTEM_PROMPT,
        model=get_chat_model(settings.llm_model),
        output_type=_SynthesisAgentOutput,
    )

    logger.debug("synthesizer starting: top_pick=%s", top_three[0].sailing_id)
    result = await Runner.run(agent, user_message)
    raw = result.final_output_as(_SynthesisAgentOutput)

    # Truncate at sentence boundary to fit MatchResult's char caps.
    output = SynthesisOutput(
        top_pick_reasoning=_truncate_to_char_limit(raw.top_pick_reasoning, _TOP_PICK_TRUNC),
        counter_memo=_truncate_to_char_limit(raw.counter_memo, _COUNTER_MEMO_TRUNC),
    )
    logger.info(
        "synthesizer done: top_pick=%s reasoning=%d/%d chars memo=%d/%d chars",
        top_three[0].sailing_id,
        len(output.top_pick_reasoning),
        len(raw.top_pick_reasoning),
        len(output.counter_memo),
        len(raw.counter_memo),
    )
    return output
