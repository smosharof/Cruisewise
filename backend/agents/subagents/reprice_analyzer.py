"""
Reprice analyzer sub-agent — LLM-gated reasoning layer for Watch flow.

Called only after price_math clears the numeric threshold, so the LLM sees
only snapshots that are already financially interesting. This keeps token usage
low and prevents the model from second-guessing pure arithmetic.

Stub: no LLM calls yet.
"""

from __future__ import annotations

import logging

from backend.schemas import PriceSnapshot
from backend.tools.price_math import BenefitCalc

logger = logging.getLogger(__name__)


async def analyze_reprice(snapshot: PriceSnapshot, calc: BenefitCalc) -> str:
    """Produce a plain-English reprice rationale paragraph.

    Final architecture:
      1. LLM call: given snapshot delta and BenefitCalc numbers, explain the
         opportunity in terms a traveller will understand (not financial jargon)
      2. Return the reasoning string for inclusion in the draft email
    """
    raise NotImplementedError("reprice_analyzer not yet implemented")
