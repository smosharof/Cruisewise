"""Unit tests for the deterministic price math tool."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.schemas import PriceSnapshot
from backend.tools.price_math import REPRICE_THRESHOLD_USD, compute_benefit, perk_value


def _snap(price: int, perks: list[str] | None = None) -> PriceSnapshot:
    return PriceSnapshot(
        booking_id="b1",
        checked_at=datetime.now(tz=UTC),
        current_price_usd=price,
        current_perks=perks or [],
        source="mock",
    )


class TestPerkValue:
    def test_known_perk(self) -> None:
        assert perk_value(["beverage_package"]) == 90

    def test_unknown_perk_is_zero(self) -> None:
        assert perk_value(["mystery_perk"]) == 0

    def test_multiple_perks(self) -> None:
        val = perk_value(["beverage_package", "wifi"])
        assert val == 90 + 25

    def test_empty_list(self) -> None:
        assert perk_value([]) == 0

    def test_case_insensitive(self) -> None:
        assert perk_value(["Beverage_Package"]) == 90


class TestComputeBenefit:
    def test_returns_benefit_calc_typeddict(self) -> None:
        snap = _snap(1000)
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        # TypedDict — check all expected keys are present
        assert "original_price_usd" in result
        assert "new_price_usd" in result
        assert "price_delta_usd" in result
        assert "perk_delta_usd" in result
        assert "perk_delta_description" in result
        assert "estimated_net_benefit_usd" in result
        assert "worth_repricing" in result

    def test_prices_are_integers(self) -> None:
        snap = _snap(1000)
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        assert isinstance(result["original_price_usd"], int)
        assert isinstance(result["new_price_usd"], int)
        assert isinstance(result["price_delta_usd"], int)
        assert isinstance(result["estimated_net_benefit_usd"], int)

    def test_clear_price_drop_triggers_reprice(self) -> None:
        snap = _snap(1000)
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        assert result["original_price_usd"] == 1200
        assert result["new_price_usd"] == 1000
        assert result["price_delta_usd"] == 200
        assert result["perk_delta_usd"] == 0
        assert result["estimated_net_benefit_usd"] == 200
        assert result["worth_repricing"] is True

    def test_small_drop_below_threshold_not_worth_it(self) -> None:
        snap = _snap(1170)
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        assert result["price_delta_usd"] == 30
        assert result["estimated_net_benefit_usd"] == 30
        assert result["worth_repricing"] is False

    def test_price_rise_not_worth_repricing(self) -> None:
        snap = _snap(1300)
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        assert result["price_delta_usd"] == -100
        assert result["worth_repricing"] is False

    def test_perk_upgrade_pushes_over_threshold(self) -> None:
        snap = _snap(1200, perks=["beverage_package"])
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        assert result["price_delta_usd"] == 0
        assert result["perk_delta_usd"] == 90
        assert result["estimated_net_benefit_usd"] == 90
        assert result["worth_repricing"] is True

    def test_perk_downgrade_offsets_price_drop(self) -> None:
        snap = _snap(1140, perks=[])
        result = compute_benefit(
            snap, price_paid_usd=1200, perks_at_booking=["beverage_package"]
        )
        # price saves 60, but loses 90 in perks → net -30
        assert result["price_delta_usd"] == 60
        assert result["perk_delta_usd"] == -90
        assert result["estimated_net_benefit_usd"] == -30
        assert result["worth_repricing"] is False

    def test_threshold_boundary_exact(self) -> None:
        snap = _snap(1200 - REPRICE_THRESHOLD_USD)
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        assert result["worth_repricing"] is True

    def test_perk_description_is_non_empty_string(self) -> None:
        snap = _snap(1000, perks=["beverage_package"])
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=[])
        assert isinstance(result["perk_delta_description"], str)
        assert len(result["perk_delta_description"]) > 0

    def test_unchanged_perks_description(self) -> None:
        snap = _snap(1000, perks=["beverage_package"])
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=["beverage_package"])
        assert "unchanged" in result["perk_delta_description"].lower()

    def test_gained_and_lost_perks_in_description(self) -> None:
        snap = _snap(1100, perks=["wifi"])
        result = compute_benefit(snap, price_paid_usd=1200, perks_at_booking=["beverage_package"])
        desc = result["perk_delta_description"]
        assert "Gains" in desc or "Loses" in desc

    def test_original_and_new_price_match_inputs(self) -> None:
        snap = _snap(850)
        result = compute_benefit(snap, price_paid_usd=1100, perks_at_booking=[])
        assert result["original_price_usd"] == 1100
        assert result["new_price_usd"] == 850
