"""
Tests for Stage 4: Container Optimizer.
"""
import pytest
from app.optimizers.container import optimize_container, ContainerResult


class TestContainerOptimizer:
    def test_returns_list_of_container_results(self):
        results = optimize_container(
            pallet_height_m=1.2, cartons_per_pallet=48,
            units_per_carton=24, shipment_quantity=100000,
            carton_length_mm=380, carton_width_mm=290, carton_height_mm=250,
        )
        assert isinstance(results, list)
        assert len(results) >= 1
        assert isinstance(results[0], ContainerResult)

    def test_best_container_first(self):
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        assert results[0].is_best is True

    def test_all_three_types_evaluated(self):
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        types = {r.container_type for r in results}
        assert "20GP" in types
        assert "40GP" in types or "40HC" in types  # at least one 40-footer

    def test_utilization_percentage_reasonable(self):
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        for r in results:
            assert 0 <= r.utilization_pct <= 100, f"Utilization {r.utilization_pct}% out of range"

    def test_empty_space_positive(self):
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        for r in results:
            assert r.empty_space_per_container_m3 >= 0
            assert r.empty_space_total_m3 >= 0

    def test_empty_space_complements_utilisation(self):
        """
        Each empty-space figure must be the complement of its own utilisation.
        Mixing the two views is the defect this vocabulary exists to prevent.
        """
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        for r in results:
            filled = r.container_volume_m3 - r.empty_space_per_container_m3
            assert filled / r.container_volume_m3 * 100 == pytest.approx(
                r.capacity_utilization_pct, abs=0.05
            )

    def test_capacity_and_shipment_views_are_distinct(self):
        """A tiny order packs densely but utilises almost none of what it books."""
        results = optimize_container(1.2, 48, 24, 100, 380, 290, 250)
        best = results[0]
        assert best.capacity_utilization_pct > 10
        assert best.utilization_pct < 5
        assert best.total_units_shipped == 100

    def test_freight_cost_positive(self):
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        for r in results:
            assert r.freight_cost_per_container > 0

    def test_containers_needed_positive(self):
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        for r in results:
            assert r.containers_needed >= 1

    def test_40ft_more_units_than_20ft(self):
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        gp20 = next((r for r in results if r.container_type == "20GP"), None)
        gp40 = next((r for r in results if r.container_type == "40GP"), None)
        if gp20 and gp40:
            assert gp40.cartons_per_container > gp20.cartons_per_container

    def test_booked_containers_cover_the_shipment(self):
        """
        The containers booked must hold the whole order.

        This was `total_units >= 100000`, where `total_units` meant capacity across
        every container — a quantity that made a 20GP look like it out-shipped a
        40GP. The real requirement is that capacity × containers covers the order.
        """
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        for r in results:
            assert r.units_per_container * r.containers_needed >= 100000
            assert r.total_units_shipped == 100000

    def test_calculates_carton_volume_internally(self):
        """Should compute carton_volume_m3 from dimensions when not provided."""
        results = optimize_container(1.2, 48, 24, 100000, 380, 290, 250)
        assert len(results) >= 1

    def test_explicit_carton_volume(self):
        """Providing carton_volume_m3 explicitly should also work."""
        results = optimize_container(
            pallet_height_m=1.2, cartons_per_pallet=48,
            units_per_carton=24, shipment_quantity=100000,
            carton_volume_m3=0.027,  # 380*290*250 / 1e9 ≈ 0.0276
        )
        assert len(results) >= 1

    def test_edge_case_small_shipment(self):
        results = optimize_container(1.2, 48, 24, 100, 380, 290, 250)
        assert results[0].containers_needed == 1
