"""Router smoke tests — all endpoints must respond without crashing."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import (
    CabinCategory,
    MatchResult,
    ShipAssessment,
)


@pytest.fixture(scope="module")
def client():
    # Mock DB pool so the lifespan can complete without a real Postgres connection.
    # Router tests exercise HTTP wiring and stub logic only, not DB state.
    with (
        patch("backend.main.init_pool", new_callable=AsyncMock),
        patch("backend.main.close_pool", new_callable=AsyncMock),
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@asynccontextmanager
async def _fake_acquire_factory(row=None, val=None):
    """Yields a fake connection whose execute/fetchrow/fetchval are no-ops by default."""
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=row)
    conn.fetchval = AsyncMock(return_value=val)
    yield conn


def _stub_match_result() -> MatchResult:
    """Build a minimal valid MatchResult for tests that mock run_match."""
    sailing = ShipAssessment(
        sailing_id="ccl-test-0101",
        cruise_line="Carnival",
        ship_name="Test Ship",
        departure_date="2026-09-01",
        return_date="2026-09-08",
        duration_nights=7,
        departure_port="MIA",
        itinerary_summary="Test Caribbean itinerary",
        cabin_price_usd=1500,
        cabin_category_priced=CabinCategory.BALCONY,
        vibe_score=0.7,
        fit_reasoning="Test fit reasoning referencing primary_vibe and budget.",
        strengths=["s1", "s2"],
        concerns=["c1", "c2"],
        review_sentiment_summary="Stub review summary.",
        booking_affiliate_url="https://partner.example.com/book?sailing=ccl-test-0101&ref=cruisewise",
    )
    return MatchResult(
        intake_id="00000000-0000-0000-0000-000000000001",
        generated_at=datetime.now(tz=UTC),
        ranked_candidates=[sailing],
        top_pick_reasoning="Stub top pick reasoning.",
        counter_memo="Stub counter memo.",
        gaps_identified=[],
        refinement_iterations=1,
    )


def test_health(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_match_intake_returns_match_result(client: TestClient) -> None:
    payload = {
        "travel_party": "couple",
        "party_size": 2,
        "primary_vibe": "relaxation",
        "budget_per_person_usd": 2000,
        "flexible_dates": True,
        "earliest_departure": "2025-11-01",
        "latest_departure": "2025-12-31",
        "duration_nights_min": 5,
        "duration_nights_max": 14,
        "preferred_regions": ["Caribbean"],
        "departure_ports_acceptable": ["MIA"],
        "cruise_experience_level": "first_timer",
    }

    with (
        patch(
            "backend.routers.match.acquire",
            side_effect=lambda: _fake_acquire_factory(),
        ),
        patch(
            "backend.routers.match.run_match",
            new_callable=AsyncMock,
            return_value=_stub_match_result(),
        ),
    ):
        resp = client.post("/api/match/intake", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    assert "ranked_candidates" in data
    assert len(data["ranked_candidates"]) >= 1
    assert "top_pick_reasoning" in data
    assert "counter_memo" in data


def test_match_intake_no_sailings_returns_422(client: TestClient) -> None:
    from backend.errors import NoSailingsFound

    payload = {
        "travel_party": "couple",
        "party_size": 2,
        "primary_vibe": "relaxation",
        "budget_per_person_usd": 2000,
        "flexible_dates": True,
        "earliest_departure": "2025-11-01",
        "latest_departure": "2025-12-31",
        "duration_nights_min": 5,
        "duration_nights_max": 14,
        "preferred_regions": ["Antarctica"],
        "departure_ports_acceptable": ["MIA"],
        "cruise_experience_level": "first_timer",
    }

    with (
        patch(
            "backend.routers.match.acquire",
            side_effect=lambda: _fake_acquire_factory(),
        ),
        patch(
            "backend.routers.match.run_match",
            new_callable=AsyncMock,
            side_effect=NoSailingsFound("No sailings matched"),
        ),
    ):
        resp = client.post("/api/match/intake", json=payload)

    assert resp.status_code == 422


def test_match_results_not_found(client: TestClient) -> None:
    valid_uuid = str(uuid.uuid4())
    with patch(
        "backend.routers.match.acquire",
        side_effect=lambda: _fake_acquire_factory(row=None),
    ):
        resp = client.get(f"/api/match/results/{valid_uuid}")
    assert resp.status_code == 404


def test_watch_register(client: TestClient) -> None:
    booking_uuid = str(uuid.uuid4())
    payload = {
        "sailing_id": "rc-wonder-0607",
        "cruise_line": "Royal Caribbean",
        "ship_name": "Wonder of the Seas",
        "departure_date": "2026-06-07",
        "booking_id": booking_uuid,
        "user_id": str(uuid.uuid4()),
        "cabin_category": "interior",
        "price_paid_usd": 1200,
        "booking_source": "external",
        "final_payment_date": "2026-04-01",
        "created_at": "2026-01-01T00:00:00Z",
    }

    fake_pool = MagicMock()
    fake_pool.acquire = lambda: _fake_acquire_factory()

    with (
        patch("backend.routers.watch.get_pool", return_value=fake_pool),
        patch(
            "backend.routers.watch.run_price_check",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        resp = client.post("/api/watch/register", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "watching"
    assert data["booking_id"] == booking_uuid


def test_watch_status_not_found(client: TestClient) -> None:
    valid_uuid = str(uuid.uuid4())
    fake_pool = MagicMock()
    fake_pool.acquire = lambda: _fake_acquire_factory(row=None)
    with patch("backend.routers.watch.get_pool", return_value=fake_pool):
        resp = client.get(f"/api/watch/status/{valid_uuid}")
    assert resp.status_code == 404


def test_watch_check_below_threshold_returns_hold(client: TestClient) -> None:
    valid_uuid = str(uuid.uuid4())
    # _assert_owned() now reads bookings.user_id; fake fetchval returns "guest"
    # so the auth scope check matches the no-Authorization-header default.
    fake_pool = MagicMock()
    fake_pool.acquire = lambda: _fake_acquire_factory(val="guest")
    with patch(
        "backend.routers.watch.run_watch_check",
        new_callable=AsyncMock,
        return_value=None,
    ), patch("backend.routers.watch.get_pool", return_value=fake_pool):
        resp = client.post(f"/api/watch/check/{valid_uuid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "hold"
    assert "threshold" in data["reason"].lower()


def test_booking_confirm(client: TestClient) -> None:
    payload = {
        "intake_id": "i1",
        "sailing_id": "s1",
        "user_id": "u1",
    }
    resp = client.post("/api/booking/confirm", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "confirmed"
    assert data["sailing_id"] == "s1"


def test_account_me(client: TestClient) -> None:
    fake_pool = MagicMock()
    fake_pool.acquire = lambda: _fake_acquire_factory(val=3)

    with patch("backend.routers.account.get_pool", return_value=fake_pool):
        resp = client.get("/api/account/me")

    assert resp.status_code == 200
    data = resp.json()
    # No Authorization header → resolves to the literal "guest" user.
    # Email is the placeholder for guests; signed-in users get None and the
    # frontend sources email from Firebase auth state instead.
    assert data["is_guest"] is True
    assert data["user_id"] == "guest"
    assert data["email"] == "guestuser@domain.com"
    assert isinstance(data["active_watches"], int)
    assert isinstance(data["matches_run"], int)
    assert data["active_watches"] == 3
    assert data["matches_run"] == 3
