"""
Email generator tool — produces a pre-filled reprice email the user forwards
to their travel agent. Output is a plain-text artifact (no HTML email).

The draft is deterministic given its inputs; the LLM reasoning comes in via
the `rationale` argument produced by reprice_analyzer.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.tools.price_math import BenefitCalc

logger = logging.getLogger(__name__)


def draft_reprice_email(
    *,
    cruise_line: str,
    ship_name: str,
    departure_date: date,
    cabin_category: str,
    calc: BenefitCalc,
    rationale: str,
) -> tuple[str, str]:
    """Return (subject, body) for a plain-text reprice request email.

    The user fills in their travel agent's address and their own name,
    then forwards. We pre-fill everything else.
    """
    raise NotImplementedError("email_gen.draft_reprice_email not yet implemented")
