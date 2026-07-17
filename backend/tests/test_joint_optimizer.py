"""
Tests for the joint optimiser.

These assert *business outcomes*, not implementation details. The previous test
suite passed 66/66 while the optimiser shipped 37%-full containers, because every
test checked that the code did what the code did. A test that cannot fail when the
product is bad is not a test.
"""

import pytest

from app.optimizers.joint import (
    optimize_jointly,
    fit_rectangles,
    Constraints,
    SearchResult,
)

DENSITY = 0.35
WEIGHT_G = 250.0
QTY = 100_000


class TestFitRectangles:
    def test_uniform_fit(self):
        # Four 600×500 cartons tile a 1200×1000 pallet exactly.
        assert fit_rectangles(600, 500, 1200, 1000).count == 4

    def test_rotation_considered(self):
        # 1000×200 only fits rotated on a 1200×1000 pallet.
        assert fit_rectangles(1000, 200, 1200, 1000).count >= 5

    def test_mixed_beats_both_uniform_orientations(self):
        # 700×200 into a 1200×1000 pallet:
        #   unrotated  → 1 col × 5 rows            = 5
        #   rotated    → 6 cols × 1 row            = 6
        #   mixed      → 5, plus a rotated pair in
        #                the leftover 500mm margin = 7   ← wins
        r = fit_rectangles(700, 200, 1200, 1000)
        assert (r.count, r.pattern) == (7, "mixed")

    def test_rotation_alone_reported_as_uniform(self):
        # 500×400: rotating gives 3×2=6 vs 2×2=4 unrotated. No margin trick needed,
        # so the pattern must not be mislabelled "mixed".
        r = fit_rectangles(500, 400, 1200, 1000)
        assert (r.count, r.pattern) == (6, "uniform-widthwise")

    def test_oversized_item_does_not_fit(self):
        assert fit_rectangles(1500, 1500, 1200, 1000).count == 0

    def test_zero_dimensions_safe(self):
        r = fit_rectangles(0, 100, 1200, 1000)
        assert (r.count, r.pattern, r.placements) == (0, "none", ())


class TestFitPlacements:
    """
    The packing must be reported, not just counted.

    A count alone forces every consumer — pallet diagram, 3D view, loading
    instruction — to re-derive the arrangement, and for a `mixed` pattern that is
    impossible: "12 per layer" does not say where the twelfth one goes.
    """

    def test_placements_match_the_count(self):
        for item, area in [
            ((600, 500), (1200, 1000)),
            ((700, 200), (1200, 1000)),
            ((289, 328), (1200, 1000)),
        ]:
            r = fit_rectangles(item[0], item[1], area[0], area[1])
            assert len(r.placements) == r.count

    @pytest.mark.parametrize(
        "il,iw",
        [(600, 500), (700, 200), (500, 400), (289, 328), (350, 250), (1200, 1000)],
    )
    def test_placements_stay_inside_the_area(self, il, iw):
        area_l, area_w = 1200.0, 1000.0
        for p in fit_rectangles(il, iw, area_l, area_w).placements:
            w = iw if p.rotated else il
            h = il if p.rotated else iw
            assert p.x >= -1e-6 and p.y >= -1e-6
            assert p.x + w <= area_l + 1e-6, "carton hangs off the pallet length"
            assert p.y + h <= area_w + 1e-6, "carton hangs off the pallet width"

    @pytest.mark.parametrize(
        "il,iw", [(600, 500), (700, 200), (500, 400), (289, 328), (350, 250)]
    )
    def test_placements_do_not_overlap(self, il, iw):
        """Two cartons in the same space would be a load plan nobody can execute."""
        rects = []
        for p in fit_rectangles(il, iw, 1200, 1000).placements:
            w = iw if p.rotated else il
            h = il if p.rotated else iw
            rects.append((p.x, p.y, p.x + w, p.y + h))

        for i, a in enumerate(rects):
            for b in rects[i + 1 :]:
                overlap_x = min(a[2], b[2]) - max(a[0], b[0])
                overlap_y = min(a[3], b[3]) - max(a[1], b[1])
                assert overlap_x <= 1e-6 or overlap_y <= 1e-6, (
                    f"{a} overlaps {b}"
                )

    def test_mixed_layout_actually_contains_both_orientations(self):
        r = fit_rectangles(700, 200, 1200, 1000)
        assert r.pattern == "mixed"
        assert {p.rotated for p in r.placements} == {True, False}

    def test_uniform_layout_has_one_orientation(self):
        r = fit_rectangles(600, 500, 1200, 1000)
        assert len({p.rotated for p in r.placements}) == 1


class TestJointSearch:
    def test_returns_search_result(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert isinstance(r, SearchResult)
        assert r.best.is_best is True

    def test_evaluates_many_configurations(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.evaluated > 1000, "search space collapsed — check the constraints"

    def test_best_is_the_cheapest(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        for alt in r.alternatives:
            assert r.best.total_cost <= alt.total_cost

    # ── The point of the whole exercise ──────────────────────────────────────

    def test_container_utilization_is_good(self):
        """
        The business problem in the brief is 'low container utilisation'. The
        greedy pipeline this replaced achieved 36.9% on exactly these inputs.
        """
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.best.container.capacity_utilization_pct > 60.0, (
            f"only {r.best.container.capacity_utilization_pct}% packed — "
            f"the optimiser is not solving the stated problem"
        )

    def test_beats_naive_single_stack(self):
        """Double-stacking pallets must actually be exploited when it pays."""
        stacked = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        flat = optimize_jointly(
            DENSITY, WEIGHT_G, QTY, constraints=Constraints(allow_pallet_stacking=False)
        )
        assert stacked.best.total_cost <= flat.best.total_cost
        assert stacked.best.container.pallet_stack >= 1

    def test_pallet_footprint_is_well_used(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.best.pallet.footprint_utilization_pct > 75.0

    # ── Physical constraints must hold ───────────────────────────────────────

    def test_respects_carton_weight_limit(self):
        c = Constraints(max_carton_weight_kg=15.0)
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY, constraints=c)
        assert r.best.carton.carton_weight_kg <= 15.0

    def test_respects_pallet_height_limit(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.best.pallet.pallet_height_m <= Constraints().max_pallet_height_m

    def test_respects_pallet_load_limit(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.best.pallet.total_weight_kg <= Constraints().max_pallet_load_kg

    def test_respects_container_payload(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.best.container.payload_kg <= r.best.container.max_payload_kg

    def test_stacked_pallets_fit_container_height(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        b = r.best
        from app.optimizers.constants import CONTAINERS

        internal_h = CONTAINERS[b.container.container_type]["internal_h"]
        assert b.pallet.pallet_height_m * b.container.pallet_stack <= internal_h + 1e-6

    def test_carton_outer_exceeds_inner(self):
        """Board has thickness. Ignoring it is what broke the old pallet stage."""
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        c = r.best.carton
        assert c.outer_length_mm > c.inner_length_mm
        assert c.outer_width_mm > c.inner_width_mm
        assert c.outer_height_mm > c.inner_height_mm

    # ── Cost model ───────────────────────────────────────────────────────────

    def test_costs_charged_on_shipment_not_capacity(self):
        """
        Packaging is billed per pouch shipped. Billing on container *capacity*
        (the old bug) made a 1-pouch order cost as much as 28,800.
        """
        r = optimize_jointly(DENSITY, WEIGHT_G, 10)
        # Costs are rounded to paise on the way out, hence the absolute tolerance.
        assert r.best.packaging_cost == pytest.approx(
            10 * r.best.package.cost_estimate, abs=0.01
        )

    def test_total_cost_is_sum_of_parts(self):
        b = optimize_jointly(DENSITY, WEIGHT_G, QTY).best
        assert b.total_cost == pytest.approx(
            b.packaging_cost + b.carton_cost + b.freight_cost, rel=1e-6
        )

    def test_cost_scales_sublinearly_per_unit(self):
        """Bigger orders fill containers better, so unit cost must fall."""
        small = optimize_jointly(DENSITY, WEIGHT_G, 1_000).best
        large = optimize_jointly(DENSITY, WEIGHT_G, 1_000_000).best
        assert large.cost_per_unit < small.cost_per_unit

    def test_metal_costs_more_than_paper(self):
        paper = optimize_jointly(DENSITY, WEIGHT_G, QTY, material="paper").best
        metal = optimize_jointly(DENSITY, WEIGHT_G, QTY, material="metal").best
        assert metal.packaging_cost > paper.packaging_cost

    # ── Honesty of the reported metrics ──────────────────────────────────────

    def test_tiny_order_reports_near_zero_real_utilization(self):
        """
        One pouch in a 40-foot box is ~0% utilised, however neat the packing.
        Reporting capacity as if it were actual utilisation is a lie the dashboard
        would repeat.
        """
        r = optimize_jointly(DENSITY, WEIGHT_G, 1)
        assert r.best.container.utilization_pct < 1.0
        assert r.best.container.capacity_utilization_pct > 10.0

    # ── Module 6: compare the three container types ─────────────────────────

    def test_all_container_types_offered(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert set(r.by_container_type) == {"20GP", "40GP", "40HC"}

    def test_by_container_type_holds_cheapest_of_each(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        for key, cfg in r.by_container_type.items():
            assert cfg.container.container_type == key

    # ── Maximum capacity ─────────────────────────────────────────────────────

    def test_max_capacity_is_reported(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.max_capacity is not None
        assert set(r.max_by_container_type) == {"20GP", "40GP", "40HC"}

    def test_densest_is_never_cheaper_than_the_cheapest(self):
        """
        The load-bearing invariant. `best` is the global cost minimum, so any
        other configuration — including the densest — costs at least as much. If
        this ever fails, the search is not actually finding the minimum.
        """
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert r.max_capacity.total_cost >= r.best.total_cost - 0.01
        for cfg in r.max_by_container_type.values():
            assert cfg.total_cost >= r.best.total_cost - 0.01

    def test_densest_really_is_the_densest_for_its_type(self):
        """Nothing in the whole search may beat max_by_container_type on units."""
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        for ct, cfg in r.max_by_container_type.items():
            best_for_type = cfg.container.units_per_container
            for other in [r.best, *r.alternatives]:
                if other.container.container_type == ct:
                    assert other.container.units_per_container <= best_for_type

    def test_max_capacity_beats_or_equals_the_recommendation(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        same_type = r.max_by_container_type[r.best.container.container_type]
        assert (
            same_type.container.units_per_container
            >= r.best.container.units_per_container
        )

    def test_densest_config_still_obeys_every_constraint(self):
        """A capacity figure nobody can physically load is worse than useless."""
        c = Constraints()
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        for cfg in r.max_by_container_type.values():
            assert cfg.carton.carton_weight_kg <= c.max_carton_weight_kg
            assert cfg.pallet.pallet_height_m <= c.max_pallet_height_m
            assert cfg.pallet.total_weight_kg <= c.max_pallet_load_kg
            assert cfg.container.payload_kg <= cfg.container.max_payload_kg

    def test_bigger_container_holds_more_at_maximum(self):
        """Sanity: a 40HC's ceiling must exceed a 20GP's. It is a bigger box."""
        r = optimize_jointly(DENSITY, WEIGHT_G, QTY)
        by = r.max_by_container_type
        assert (
            by["40HC"].container.units_per_container
            > by["20GP"].container.units_per_container
        )

    # ── shipment_type ────────────────────────────────────────────────────────

    def test_max_containers_is_enforced(self):
        r = optimize_jointly(DENSITY, WEIGHT_G, 5_000, max_containers=1)
        assert r.best.container.containers_needed == 1

    def test_impossible_single_container_raises(self):
        with pytest.raises(ValueError, match="cannot be loaded into 1 container"):
            optimize_jointly(DENSITY, WEIGHT_G, 50_000_000, max_containers=1)

    # ── Input validation ─────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "density,weight,qty",
        [(0, 250, 100), (0.35, 0, 100), (0.35, 250, 0), (-1, 250, 100)],
    )
    def test_rejects_invalid_inputs(self, density, weight, qty):
        with pytest.raises(ValueError):
            optimize_jointly(density, weight, qty)

    def test_impossible_constraints_raise_clearly(self):
        with pytest.raises(ValueError, match="No packaging configuration"):
            optimize_jointly(
                DENSITY, WEIGHT_G, QTY, constraints=Constraints(max_carton_weight_kg=0.001)
            )

    def test_search_is_fast(self):
        import time

        t = time.perf_counter()
        optimize_jointly(DENSITY, WEIGHT_G, QTY)
        assert time.perf_counter() - t < 5.0, "exhaustive search got too slow for a request"
