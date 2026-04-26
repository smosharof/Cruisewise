"""
Reprice writer sub-agent — only invoked AFTER price_math clears the threshold.

Receives the booking, the BenefitCalc numbers, and writes the reasoning,
recommendation, confidence, and the pre-filled email the traveler can forward
to their travel agent.

Same length-budget pattern as the synthesizer: internal type with no caps for
the agent (so Gemini's structured-output validator never rejects), then truncate
at sentence boundary to fit the public schema's max_length on the way back.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from agents import Agent, Runner
from pydantic import BaseModel, Field

from backend.agents.subagents.synthesizer import _truncate_to_char_limit
from backend.config import get_settings
from backend.llm import get_chat_model
from backend.tools.price_math import BenefitCalc

logger = logging.getLogger(__name__)


class RepriceWriterOutput(BaseModel):
    """Public output — bounded to RepriceRecommendation's caps."""

    reasoning: str = Field(max_length=600, description="Why this reprice is worth acting on")
    recommendation: Literal["reprice", "rebook_same_cabin", "upgrade_cabin", "hold"]
    confidence: Literal["high", "medium", "low"]
    suggested_email_subject: str = Field(max_length=120)
    suggested_email_body: str = Field(max_length=2000)


class _RepriceAgentOutput(BaseModel):
    """Internal — no char caps so the LLM validator never rejects verbose copy."""

    reasoning: str
    recommendation: Literal["reprice", "rebook_same_cabin", "upgrade_cabin", "hold"]
    confidence: Literal["high", "medium", "low"]
    suggested_email_subject: str
    suggested_email_body: str


_REASONING_TRUNC = 550
_EMAIL_BODY_TRUNC = 1800
_EMAIL_SUBJECT_TRUNC = 110


_SYSTEM_PROMPT = """\
You are helping a traveler ask their travel agent to reprice a cruise booking.

You will receive a JSON object with:
  - booking: ship_name, cruise_line, sailing_id, departure_date, cabin_category,
    price_paid_usd, perks_at_booking, final_payment_date
  - benefit: the pre-computed price math (original_price_usd, new_price_usd,
    price_delta_usd, perk_delta_usd, perk_delta_description,
    estimated_net_benefit_usd)

The math is already done. Your job is the human layer:

REASONING (max 4 sentences)
  Plain language. Explain why this reprice is worth acting on, naming the dollar
  savings and any relevant perk changes. No financial jargon. No hedging.

RECOMMENDATION
  Pick one:
  - "reprice"           : same cabin, current rate (most common — pick this for clean savings)
  - "rebook_same_cabin" : booking line requires cancel + rebook to apply the new rate
  - "upgrade_cabin"     : the savings cover an upgrade (only when delta is large)
  - "hold"              : do not act yet (rare — usually only if perks would be lost)

CONFIDENCE
  - "high"   : clear, durable savings; no perk loss
  - "medium" : savings real but partial perk loss or modest amount
  - "low"    : savings on the threshold edge or risky to ask

SUGGESTED_EMAIL_SUBJECT (max 100 characters, plain text)
  Format: "Reprice request — <ship_name> <departure_date>"

SUGGESTED_EMAIL_BODY (max 1700 characters)
  A polite, ready-to-forward email to the user's travel agent. Required content:
    - Greeting line ("Hello,")
    - Reference the booking: ship_name, sailing departure date, cabin_category
    - State the original price the traveler paid
    - State the current rate they have observed
    - Name the dollar savings clearly
    - Note any perk delta if relevant
    - Clear ask: "Please reprice my booking to the current rate of $<new_price>."
    - Sign-off ("Thank you,")
  Do NOT invent perks, agent names, or booking numbers. Use the booking fields
  exactly as provided. Plain text — no Markdown, no bullet points.
"""


async def write_reprice(booking: dict, benefit: BenefitCalc) -> RepriceWriterOutput:
    """Run the reprice writer LLM and return the bounded output.

    booking is a dict with the fields named in the system prompt. benefit is
    the BenefitCalc TypedDict from price_math.compute_benefit.
    """
    settings = get_settings()

    user_message = json.dumps(
        {"booking": booking, "benefit": dict(benefit)},
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    agent = Agent(
        name="reprice_writer",
        instructions=_SYSTEM_PROMPT,
        model=get_chat_model(settings.llm_model),
        output_type=_RepriceAgentOutput,
    )

    logger.debug(
        "reprice_writer starting: booking=%s savings=$%d",
        booking.get("booking_id"),
        benefit["estimated_net_benefit_usd"],
    )
    result = await Runner.run(agent, user_message)
    raw = result.final_output_as(_RepriceAgentOutput)

    output = RepriceWriterOutput(
        reasoning=_truncate_to_char_limit(raw.reasoning, _REASONING_TRUNC),
        recommendation=raw.recommendation,
        confidence=raw.confidence,
        suggested_email_subject=_truncate_to_char_limit(
            raw.suggested_email_subject, _EMAIL_SUBJECT_TRUNC
        ),
        suggested_email_body=_truncate_to_char_limit(
            raw.suggested_email_body, _EMAIL_BODY_TRUNC
        ),
    )
    logger.info(
        "reprice_writer done: booking=%s rec=%s confidence=%s reasoning=%d/%d email=%d/%d",
        booking.get("booking_id"),
        output.recommendation,
        output.confidence,
        len(output.reasoning),
        len(raw.reasoning),
        len(output.suggested_email_body),
        len(raw.suggested_email_body),
    )
    return output
