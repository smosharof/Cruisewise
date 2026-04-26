"""
Notifier tool — delivers reprice alerts to the user.

MVP: logs to console. Production: swap the body of notify_reprice for
an email (SendGrid / SES) or SMS (Twilio) call without changing the signature.
"""

from __future__ import annotations

import logging

from backend.schemas import RepriceRecommendation

logger = logging.getLogger(__name__)


async def notify_reprice(user_email: str, recommendation: RepriceRecommendation) -> None:
    """Deliver a reprice recommendation to the user.

    Console-only in MVP — replace with real transport before launch.
    """
    logger.info(
        "REPRICE ALERT [console] → %s | booking=%s | net_benefit=$%.2f\n%s",
        user_email,
        recommendation.booking_id,
        recommendation.net_benefit.net_benefit_usd,
        recommendation.draft_email,
    )
