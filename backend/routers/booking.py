from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class BookingConfirmRequest(BaseModel):
    """Handoff payload: user clicked "Book" on a Match recommendation."""

    intake_id: str
    sailing_id: str
    user_id: str


class BookingAck(BaseModel):
    status: str
    sailing_id: str


@router.post("/confirm", response_model=BookingAck, status_code=201)
async def confirm_booking(request: BookingConfirmRequest) -> BookingAck:
    """Record that a user is booking a recommended sailing.

    This is a handoff trigger: it logs the conversion and can auto-register
    a Watch once the user confirms their booking details.
    """
    logger.info(
        "Booking confirm intake=%s sailing=%s user=%s",
        request.intake_id,
        request.sailing_id,
        request.user_id,
    )

    # TODO: insert into bookings (booking_source='match')
    # TODO: optionally trigger watch registration

    return BookingAck(status="confirmed", sailing_id=request.sailing_id)
