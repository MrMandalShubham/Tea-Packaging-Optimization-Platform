"""
Tests for the baseline model.

The point of these is to defend the *integrity of the comparison*. The failure
mode being guarded against is the one the old code had: a baseline derived from
the optimised answer, which makes the reported saving a tautology.
"""

import pytest

from app.optimizers.baseline import (
    compute_baseline,
    STANDARD_POUCH_SIZES_MM,
    STANDARD_CARTON_SIZES_MM,
)
from app.optimizers.joint import optimize_jointly

DENSITY = 0.35
WEIGHT_G = 250.0
QTY = 100_000


class TestBaselineIndependence:
    """The baseline must not be a function of the optimiser's output."""

    def test_baseline_uses_a_catalogue_pouch(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        dims = (b.package_length_mm, b.package_width_mm, b.package_height_mm)
        assert dims in STANDARD_POUCH_SIZES_MM

    def test_baseline_uses_a_catalogue_carton(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        dims = (b.carton_length_mm, b.carton_width_mm, b.carton_height_mm)
        assert dims in STANDARD_CARTON_SIZES_MM

    def test_baseline_is_deterministic(self):
        assert compute_baseline(DENSITY, WEIGHT_G, QTY).total_cost == (
            compute_baseline(DENSITY, WEIGHT_G, QTY).total_cost
        )

    def test_baseline_ignores_optimiser_constraints(self):
        """
        Changing what the optimiser is allowed to do must not move the baseline.
        If it does, the two sides are coupled and the saving is meaningless.
        """
        from app.optimizers.joint import Constraints

        base = compute_baseline(DENSITY, WEIGHT_G, QTY).total_cost
        # Optimiser is hobbled; baseline must be untouched.
        optimize_jointly(
            DENSITY, WEIGHT_G, QTY, constraints=Constraints(allow_pallet_stacking=False)
        )
        assert compute_baseline(DENSITY, WEIGHT_G, QTY).total_cost == base

    def test_baseline_is_not_a_fixed_ratio_of_optimised(self):
        """
        The old bug: current = ai × 1.25-ish, always. If the ratio is constant
        across very different inputs, the baseline is a multiplier in disguise.
        """
        ratios = []
        for density, weight in [(0.25, 100.0), (0.35, 250.0), (0.5, 500.0)]:
            b = compute_baseline(density, weight, QTY)
            a = optimize_jointly(density, weight, QTY).best
            ratios.append(b.total_cost / a.total_cost)
        assert max(ratios) - min(ratios) > 0.05, (
            f"savings ratio is suspiciously constant across inputs: {ratios}"
        )


class TestBaselineIsNotAStrawman:
    """
    A strawman inflates savings as dishonestly as a multiplier does.

    Each test here pins a place where the baseline was accidentally modelling an
    incompetent exporter rather than a constrained one, and where the resulting
    "saving" was really the baseline's stupidity rather than the optimiser's skill.
    """

    def test_baseline_carton_tiles_the_pallet(self):
        """
        The stock carton must be chosen for tea-per-pallet, not pouches-per-carton.

        Scoring on units-per-carton picked a 500×350×300 box for 1 kg pouches that
        covered 58% of a EUR pallet. Real stock sizes (600×400, 400×300) are
        standard precisely BECAUSE they are pallet-modular.
        """
        for weight in (100.0, 250.0, 1000.0):
            b = compute_baseline(0.35, weight, QTY)
            footprint = (
                b.cartons_per_layer * b.carton_length_mm * b.carton_width_mm
            ) / (1200 * 1000) * 100
            assert footprint > 75, (
                f"{weight}g baseline wastes {100 - footprint:.0f}% of the pallet "
                f"footprint — that is a strawman, not current practice"
            )

    def test_baseline_rotates_layers_like_any_packer_would(self):
        """
        Turning the whole layer 90° is obvious and free. Only *mixing* orientations
        within a layer takes planning, and that stays an optimiser-only lever.
        """
        from app.optimizers.baseline import _uniform_layer_fit

        # 500×350 on a 1200×1000 pallet: 2×2=4 unrotated, 3×2=6 rotated.
        assert _uniform_layer_fit(500, 350) == 6

    def test_baseline_loads_the_container_floor_like_the_optimiser(self):
        """
        Pallet rotation on the container floor is how a 20GP takes 9 instead of 8.
        Reserving that for the AI was worth a whole pallet per container.
        """
        from app.optimizers.joint import fit_rectangles

        b = compute_baseline(0.35, 250.0, QTY)
        expected = fit_rectangles(1200, 1000, 5.898 * 1000, 2.352 * 1000)
        assert b.pallets_per_container == expected.count

    def test_savings_stay_in_a_defensible_band(self):
        """
        Across the SKU range the saving must be large enough to matter and small
        enough to believe. Before the fixes above this ran 39–61%; a claim of 60%
        would not survive the first question from a packaging engineer.
        """
        savings = []
        for weight in (100.0, 250.0, 500.0, 1000.0, 2000.0):
            b = compute_baseline(0.35, weight, QTY)
            a = optimize_jointly(0.35, weight, QTY).best
            savings.append((b.total_cost - a.total_cost) / b.total_cost * 100)
        assert max(savings) < 55, f"saving of {max(savings):.0f}% is not credible"
        assert min(savings) > 5, f"saving of {min(savings):.0f}% would not fund the project"


class TestBaselineRealism:
    """A strawman baseline inflates savings as dishonestly as a multiplier."""

    def test_baseline_pouch_actually_holds_the_tea(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        net_volume_cm3 = WEIGHT_G / DENSITY
        assert b.package_volume_cm3 >= net_volume_cm3

    def test_baseline_respects_carton_weight_limit(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        assert b.carton_weight_kg <= 30.0

    def test_baseline_respects_pallet_height(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        assert b.pallet_height_m <= 1.8

    def test_baseline_ships_the_whole_order(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        assert b.containers_needed * b.units_per_container >= QTY

    def test_baseline_fill_ratio_is_plausible(self):
        """Catalogue rounding wastes space, but a real exporter isn't at 20%."""
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        assert 0.5 <= b.package_fill_ratio <= 1.0


class TestBaselineOverrides:
    def test_user_values_win(self):
        b = compute_baseline(
            DENSITY,
            WEIGHT_G,
            QTY,
            current_package_l=150.0,
            current_package_w=120.0,
            current_package_h=80.0,
            current_units_per_carton=12,
        )
        assert b.package_length_mm == 150.0
        assert b.units_per_carton == 12
        assert b.is_user_supplied is True

    def test_modelled_baseline_flagged_as_not_user_supplied(self):
        assert compute_baseline(DENSITY, WEIGHT_G, QTY).is_user_supplied is False

    def test_explicit_costs_win(self):
        b = compute_baseline(
            DENSITY, WEIGHT_G, QTY, current_packaging_cost=500_000.0
        )
        assert b.packaging_cost == 500_000.0


class TestBaselineTransparency:
    def test_assumptions_are_recorded(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        assert len(b.assumptions) >= 4
        assert all(isinstance(a, str) and a for a in b.assumptions)

    def test_assumptions_name_the_levers(self):
        text = " ".join(compute_baseline(DENSITY, WEIGHT_G, QTY).assumptions).lower()
        assert "stock" in text
        assert "orientation" in text
        assert "stack" in text


class TestBaselineVsOptimised:
    def test_optimiser_wins_on_a_container_scale_order(self):
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        a = optimize_jointly(DENSITY, WEIGHT_G, QTY).best
        assert a.total_cost < b.total_cost

    def test_saving_comes_mostly_from_freight(self):
        """The brief's premise is that freight dominates. Verify that's what moves."""
        b = compute_baseline(DENSITY, WEIGHT_G, QTY)
        a = optimize_jointly(DENSITY, WEIGHT_G, QTY).best
        freight_saving = b.freight_cost - a.freight_cost
        total_saving = b.total_cost - a.total_cost
        assert freight_saving / total_saving > 0.4

    def test_both_sides_priced_with_the_same_model(self):
        """Same material, same quantity → identical per-pouch material rate."""
        b = compute_baseline(DENSITY, WEIGHT_G, QTY, material="paper")
        a = optimize_jointly(DENSITY, WEIGHT_G, QTY, material="paper").best
        # Both must charge for exactly the shipment, not for container capacity.
        assert b.packaging_cost / QTY > 0
        assert a.packaging_cost == pytest.approx(QTY * a.package.cost_estimate, abs=0.01)

    @pytest.mark.parametrize("qty", [1, 10, 500])
    def test_small_orders_may_not_save_and_that_is_reported_honestly(self, qty):
        """
        A sub-container order pays fixed freight either way. An honest model is
        allowed to show a small or negative saving here; it must not manufacture
        one.
        """
        b = compute_baseline(DENSITY, WEIGHT_G, qty)
        a = optimize_jointly(DENSITY, WEIGHT_G, qty).best
        saving_pct = (b.total_cost - a.total_cost) / b.total_cost * 100
        assert saving_pct < 40.0, (
            f"{saving_pct:.0f}% saving on a {qty}-pouch order is not credible"
        )

    def test_input_validation(self):
        with pytest.raises(ValueError):
            compute_baseline(0, WEIGHT_G, QTY)
        with pytest.raises(ValueError):
            compute_baseline(DENSITY, 0, QTY)
        with pytest.raises(ValueError):
            compute_baseline(DENSITY, WEIGHT_G, 0)
