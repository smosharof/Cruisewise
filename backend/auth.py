"""Firebase ID token verification for FastAPI dependencies.

Initializes the Firebase Admin SDK using Application Default Credentials —
the same ADC the rest of the app uses for Vertex AI and Cloud SQL — so no
extra service-account JSON is needed in the container. If ADC is unavailable
(local dev without `gcloud auth application-default login`) we still allow
the module to import, and any verify call will raise rather than crashing
startup. This mirrors the defensive init pattern already used in
``backend/llm.py``.
"""

from __future__ import annotations

import logging

import firebase_admin
from fastapi import Header, HTTPException
from firebase_admin import auth as firebase_auth

logger = logging.getLogger(__name__)

_init_error: Exception | None = None
try:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
except Exception as e:  # pragma: no cover - depends on ambient ADC
    _init_error = e
    logger.warning("Firebase Admin init deferred: %s", e)


async def get_current_user_id(authorization: str = Header(default=None)) -> str | None:
    """Verify a `Bearer <id_token>` Authorization header. Returns the Firebase
    UID on success, raises 401 on bad tokens, returns None when no header is
    sent (caller decides whether anonymous is allowed)."""
    if authorization is None:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    if _init_error is not None:
        raise HTTPException(status_code=503, detail="Auth backend not initialized")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e


async def get_user_id_or_guest(authorization: str = Header(default=None)) -> str:
    """Like :func:`get_current_user_id` but tolerant: returns a string id for
    every caller. Bearer tokens resolve to the Firebase UID; ``Guest <uuid>``
    headers pass the guest UUID through; anything else (or a verify failure)
    becomes the literal string ``"guest"``."""
    if authorization is None:
        return "guest"

    if authorization.startswith("Bearer "):
        if _init_error is not None:
            return "guest"
        token = authorization.removeprefix("Bearer ").strip()
        try:
            decoded = firebase_auth.verify_id_token(token)
            return decoded["uid"]
        except Exception:
            return "guest"

    if authorization.startswith("Guest "):
        guest_id = authorization.removeprefix("Guest ").strip()
        return guest_id or "guest"

    return "guest"
