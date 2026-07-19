"""
Integration tests for the full 5-stage optimization pipeline.
"""
import pytest
from app.services.simulation_service import (
    run_full_pipeline,
    PipelineResult,
    CurrentEstimate,
)
from app.optimizers.package import PackageResult
from app.optimizers.carton import CartonResult
from app.optimizers.pallet import PalletResult
from app.optimizers.container import ContainerResult


class TestFullPipeline:
    """End-to-end pipeline tests."""

    def test_pipeline_returns_pipeline_result(self):
        result = run_full_pipeline(
            tea_density=0.35, package_weight=250.0, shipment_quantity=100000,
        )
        assert isinstance(result, PipelineResult)

    def test_all_stages_populated(self):
        result = run_full_pipeline(0.35, 250.0, 100000)
        assert result.best_package is not None
        assert result.carton is not None
        assert result.pallet is not None
        assert result.best_container is not None

    def test_package_alternatives_exist(self):
        result = run_full_pipeline(0.35, 250.0, 100000)
        assert len(result.package_alternatives) >= 1

    def test_container_alternatives_exist(self):
        result = run_full_pipeline(0.35, 250.0, 100000)
        assert len(result.container_alternatives) >= 1

    def test_cost_summary_positive(self):
        result = run_full_pipeline(0.35, 250.0, 100000)
        assert result.packaging_cost > 0
        assert result.freight_cost > 0
        assert result.total_cost > 0

    def test_savings_positive(self):
        result = run_full_pipeline(0.35, 250.0, 100000)
        assert result.total_savings > 0, "AI should always save money vs naive estimate"

    def test_comparison_rows_exist(self):
        result = run_full_pipeline(0.35, 250.0, 100000)
        assert len(result.comparison) >= 6  # at least 6 parameters

    def test_current_estimate_populated(self):
        result = run_full_pipeline(0.35, 250.0, 100000)
        assert result.current is not None
        assert result.current.total_cost > result.total_cost

    def test_round_shape_works(self):
        result = run_full_pipeline(0.35, 250.0, 100000, package_shape="round")
        assert result.best_package.shape == "round"

    def test_plastic_material_works(self):
        result = run_full_pipeline(0.35, 250.0, 100000, packaging_material="plastic")
        assert result.packaging_cost > 0

    def test_metal_material_works(self):
        result = run_full_pipeline(0.35, 250.0, 100000, packaging_material="metal")
        assert result.packaging_cost > 0

    def test_metal_is_most_expensive(self):
        paper = run_full_pipeline(0.35, 250.0, 100000, packaging_material="paper")
        plastic = run_full_pipeline(0.35, 250.0, 100000, packaging_material="plastic")
        metal = run_full_pipeline(0.35, 250.0, 100000, packaging_material="metal")
        assert metal.packaging_cost > plastic.packaging_cost > paper.packaging_cost

    def test_custom_current_values_accepted(self):
        result = run_full_pipeline(
            0.35, 250.0, 100000,
            current_package_l=150.0, current_package_w=120.0, current_package_h=80.0,
            current_units_per_carton=12, current_packaging_cost=500000.0,
        )
        assert result.current is not None
        assert result.current.package_length_mm == 150.0
        assert result.current.units_per_carton == 12

    def test_large_shipment_scales_containers(self):
        small = run_full_pipeline(0.35, 250.0, 10000)
        large = run_full_pipeline(0.35, 250.0, 1000000)
        assert large.best_container.containers_needed > small.best_container.containers_needed

    def test_green_tea_density_works(self):
        result = run_full_pipeline(0.32, 250.0, 100000)  # green tea
        assert result.best_package is not None

    def test_herbal_tea_low_density(self):
        result = run_full_pipeline(0.22, 250.0, 100000)  # herbal
        assert result.best_package.volume_cm3 > 0


class TestResultCoherence:
    """
    The parts of the recommendation must describe the same physical solution.

    Every bug below was found by opening the page and reading it, not by the test
    suite — which passed throughout. They are pinned here so they stay fixed.
    """

    def test_best_package_is_the_one_inside_the_carton(self):
        """
        The pouch shown as "Best" must be the pouch the carton was built from.

        `optimize_package` ranks on pouch material alone and always crowns a cube;
        the joint search usually picks something else because a cube tiles badly.
        Carrying the package stage's ranking through meant the UI showed a 93.7 mm
        cube as Best while the carton held a 93 × 79 × 112 pouch.
        """
        r = run_full_pipeline(0.35, 250.0, 100000)
        nx, ny, nz = r.carton.arrangement
        gap = 2.0

        implied_l = (r.carton.inner_length_mm - (nx - 1) * gap) / nx
        implied_w = (r.carton.inner_width_mm - (ny - 1) * gap) / ny
        implied_h = (r.carton.inner_height_mm - (nz - 1) * gap) / nz

        assert implied_l == pytest.approx(r.best_package.length_mm, abs=0.15)
        assert implied_w == pytest.approx(r.best_package.width_mm, abs=0.15)
        assert implied_h == pytest.approx(r.best_package.height_mm, abs=0.15)

    def test_best_package_is_flagged_best(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert r.best_package.is_best is True
        assert r.best_package.rank == 1

    def test_alternatives_are_not_flagged_best(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert all(p.is_best is False for p in r.package_alternatives)

    def test_no_duplicate_package_alternatives(self):
        """Several configurations share a pouch; listing it twice is noise."""
        r = run_full_pipeline(0.35, 250.0, 100000)
        dims = [
            (p.length_mm, p.width_mm, p.height_mm)
            for p in [r.best_package, *r.package_alternatives]
        ]
        assert len(dims) == len(set(dims))

    def test_alternative_ranks_are_sequential(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        ranks = [p.rank for p in [r.best_package, *r.package_alternatives]]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_carton_outer_matches_inner_plus_board(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        c = r.carton
        expected = c.inner_length_mm + 2 * c.board_thickness_mm
        assert c.outer_length_mm == pytest.approx(expected, abs=0.15)

    def test_costs_reconcile_to_total(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert r.total_cost == pytest.approx(
            r.packaging_cost + r.carton_cost + r.freight_cost, abs=0.05
        )

    def test_savings_equals_baseline_minus_total(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert r.total_savings == pytest.approx(
            r.current.total_cost - r.total_cost, abs=0.05
        )

    def test_container_alternatives_are_distinct_types(self):
        """The DB enforces one row per (simulation, container_type)."""
        r = run_full_pipeline(0.35, 250.0, 100000)
        types = [c.container_type for c in r.container_alternatives]
        assert len(types) == len(set(types))
        assert r.best_container.container_type not in types

    def test_every_comparison_row_explains_itself(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert all(row.driver for row in r.comparison), "a row has no stated driver"


class TestModule3ProductVolume:
    """
    The brief requires Product Volume as a distinct output from pouch volume.

    It used to be a local variable inside optimize_package, discarded before the
    result was built — so the API could not report it and the UI would have had to
    recompute `weight / density` itself.
    """

    def test_product_volume_is_mass_over_density(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert r.best_package.product_volume_cm3 == pytest.approx(250.0 / 0.35, abs=0.02)

    def test_pouch_volume_exceeds_product_volume(self):
        """Tea needs headspace; a pouch sized exactly to the tea cannot be sealed."""
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert r.best_package.volume_cm3 > r.best_package.product_volume_cm3

    def test_headspace_is_the_difference(self):
        p = run_full_pipeline(0.35, 250.0, 100000).best_package
        assert p.headspace_cm3 == pytest.approx(
            p.volume_cm3 - p.product_volume_cm3, abs=0.02
        )

    def test_product_volume_scales_with_density(self):
        light = run_full_pipeline(0.22, 250.0, 100000).best_package
        dense = run_full_pipeline(0.45, 250.0, 100000).best_package
        assert light.product_volume_cm3 > dense.product_volume_cm3

    def test_alternatives_share_the_product_volume(self):
        """Product volume depends only on the inputs, not on the pouch chosen."""
        r = run_full_pipeline(0.35, 250.0, 100000)
        for alt in r.package_alternatives:
            assert alt.product_volume_cm3 == pytest.approx(
                r.best_package.product_volume_cm3, abs=0.02
            )


class TestModule6ContainerMetrics:
    """
    Module 6 requires Empty Space and Total Units alongside utilisation.

    Each must belong to exactly one view. Conflating them is what made a 20GP
    appear to out-ship a 40GP.
    """

    def test_total_units_is_per_container(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        c = r.best_container
        assert c.units_per_container == c.cartons_per_container * r.carton.units_per_carton

    def test_shipped_units_is_the_order(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        assert r.best_container.total_units_shipped == 100000

    def test_empty_space_per_container_complements_packing_density(self):
        c = run_full_pipeline(0.35, 250.0, 100000).best_container
        filled = c.container_volume_m3 - c.empty_space_per_container_m3
        assert filled / c.container_volume_m3 * 100 == pytest.approx(
            c.capacity_utilization_pct, abs=0.05
        )

    def test_empty_space_total_complements_shipment_utilisation(self):
        c = run_full_pipeline(0.35, 250.0, 100000).best_container
        booked = c.containers_needed * c.container_volume_m3
        filled = booked - c.empty_space_total_m3
        assert filled / booked * 100 == pytest.approx(c.utilization_pct, abs=0.05)

    def test_bigger_container_holds_more_per_container(self):
        """The comparison that the old ambiguous field got backwards."""
        r = run_full_pipeline(0.35, 250.0, 100000)
        by_type = {k: c.container for k, c in r.configurations_by_container.items()}
        assert by_type["40GP"].units_per_container > by_type["20GP"].units_per_container

    def test_smaller_container_needs_more_boxes(self):
        r = run_full_pipeline(0.35, 250.0, 100000)
        by_type = {k: c.container for k, c in r.configurations_by_container.items()}
        assert by_type["20GP"].containers_needed > by_type["40GP"].containers_needed


class TestPackageWeightRange:
    """
    The API used to reject weights the engine handles. `le=500` was a magic
    literal repeated across three schemas, blocking 1 kg — a common tea SKU.
    """

    @pytest.mark.parametrize("weight", [25.0, 100.0, 250.0, 500.0, 1000.0, 2000.0])
    def test_catalogue_weights_all_optimise(self, weight):
        r = run_full_pipeline(0.35, weight, 50000)
        assert r.total_cost > 0
        assert r.best_container.containers_needed >= 1

    def test_heavier_pouches_mean_fewer_per_carton(self):
        light = run_full_pipeline(0.35, 100.0, 50000)
        heavy = run_full_pipeline(0.35, 1000.0, 50000)
        assert heavy.carton.units_per_carton < light.carton.units_per_carton

    def test_carton_weight_limit_still_respected_at_2kg(self):
        r = run_full_pipeline(0.35, 2000.0, 50000)
        assert r.carton.carton_weight_kg <= 25.0


class TestShipmentType:
    def test_per_container_forces_one_container(self):
        r = run_full_pipeline(0.35, 250.0, 5000, shipment_type="per_container")
        assert r.best_container.containers_needed == 1

    def test_total_weight_allows_many_containers(self):
        r = run_full_pipeline(0.35, 250.0, 1_000_000, shipment_type="total_weight")
        assert r.best_container.containers_needed > 1

    def test_per_container_rejects_impossible_order(self):
        with pytest.raises(ValueError, match="cannot be loaded into 1 container"):
            run_full_pipeline(0.35, 250.0, 50_000_000, shipment_type="per_container")

    def test_unknown_shipment_type_rejected(self):
        with pytest.raises(ValueError, match="Unknown shipment_type"):
            run_full_pipeline(0.35, 250.0, 1000, shipment_type="nonsense")


class TestPalletType:
    """
    The pallet is an input (the exporter's fleet dictates it), not an optimisation
    variable. Both sides of the comparison must ride the selected pallet.
    """

    def test_default_is_industrial_and_matches_explicit(self):
        implicit = run_full_pipeline(0.35, 250.0, 100_000)
        explicit = run_full_pipeline(0.35, 250.0, 100_000, pallet_type="industrial")
        assert implicit.total_cost == explicit.total_cost
        assert implicit.current.total_cost == explicit.current.total_cost

    def test_eur1_changes_the_physics(self):
        ind = run_full_pipeline(0.35, 250.0, 100_000, pallet_type="industrial")
        eur = run_full_pipeline(0.35, 250.0, 100_000, pallet_type="eur1")
        # A 1200x800 deck holds fewer/different cartons than 1200x1000 —
        # identical results would mean the parameter is not actually wired in.
        assert (
            eur.pallet.cartons_per_layer != ind.pallet.cartons_per_layer
            or eur.total_cost != ind.total_cost
        )

    def test_baseline_rides_the_same_pallet(self):
        eur = run_full_pipeline(0.35, 250.0, 100_000, pallet_type="eur1")
        ind = run_full_pipeline(0.35, 250.0, 100_000, pallet_type="industrial")
        # The baseline must move with the pallet too, or the saving silently
        # includes a pallet swap the exporter never made.
        assert eur.current.total_cost != ind.current.total_cost

    def test_gma_works_and_savings_stay_defensible(self):
        for key in ("industrial", "eur1", "gma"):
            r = run_full_pipeline(0.35, 250.0, 100_000, pallet_type=key)
            pct = r.total_savings / r.current.total_cost * 100
            assert 0 < pct < 55, f"{key}: {pct:.1f}%"

    def test_unknown_pallet_type_rejected(self):
        with pytest.raises(ValueError, match="Unknown pallet_type"):
            run_full_pipeline(0.35, 250.0, 1000, pallet_type="wood")
