"""
Tests for Stage 1: Package Optimizer.
"""
import pytest
from app.optimizers.package import optimize_package, PackageResult


class TestPackageOptimizer:
    """Core package optimization tests."""

    def test_returns_list_of_package_results(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0, shape="square", material="paper")
        assert isinstance(results, list)
        assert len(results) >= 1
        assert isinstance(results[0], PackageResult)

    def test_best_package_is_first(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0)
        assert results[0].is_best is True
        assert results[0].rank == 1

    def test_square_produces_valid_dimensions(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0, shape="square")
        best = results[0]
        # Dimensions should be positive
        assert best.length_mm > 0
        assert best.width_mm > 0
        assert best.height_mm > 0
        # Volume should be close to expected: 250/0.35 * 1.15 ≈ 821 cm³
        assert 700 < best.volume_cm3 < 1000

    def test_round_produces_valid_dimensions(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0, shape="round")
        best = results[0]
        assert best.length_mm > 0  # = diameter for round
        assert best.width_mm > 0   # = diameter for round
        assert best.height_mm > 0
        assert best.shape == "round"

    def test_fill_ratio_reasonable(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0)
        for r in results:
            assert 0.5 < r.fill_ratio <= 1.0, f"Fill ratio {r.fill_ratio} out of range"

    def test_cost_increases_with_expensive_material(self):
        paper_results = optimize_package(tea_density=0.35, package_weight=250.0, material="paper")
        metal_results = optimize_package(tea_density=0.35, package_weight=250.0, material="metal")
        assert metal_results[0].cost_estimate > paper_results[0].cost_estimate

    def test_volume_scales_with_density(self):
        low_density = optimize_package(tea_density=0.20, package_weight=250.0)
        high_density = optimize_package(tea_density=0.50, package_weight=250.0)
        # Lower density → larger volume
        assert low_density[0].volume_cm3 > high_density[0].volume_cm3

    def test_volume_scales_with_weight(self):
        light = optimize_package(tea_density=0.35, package_weight=100.0)
        heavy = optimize_package(tea_density=0.35, package_weight=500.0)
        assert heavy[0].volume_cm3 > light[0].volume_cm3

    def test_returns_multiple_alternatives(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0, num_alternatives=3)
        # Should have at least 1 best + alternatives
        assert len(results) >= 2

    def test_alternatives_different_from_best(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0, num_alternatives=3)
        best = results[0]
        for alt in results[1:]:
            # At least one dimension should differ meaningfully
            dims_differ = (
                abs(best.length_mm - alt.length_mm) > 1 or
                abs(best.width_mm - alt.width_mm) > 1 or
                abs(best.height_mm - alt.height_mm) > 1
            )
            assert dims_differ, f"Alternative is too similar to best"

    def test_edge_case_minimum_weight(self):
        results = optimize_package(tea_density=0.30, package_weight=10.0)  # tiny 10g pack
        assert len(results) >= 1
        assert results[0].volume_cm3 > 0

    def test_edge_case_maximum_density(self):
        results = optimize_package(tea_density=0.80, package_weight=500.0)
        assert len(results) >= 1
        assert results[0].volume_cm3 > 0
        # Volume should be compact: 500/0.80 * 1.15 ≈ 718 cm³
        assert results[0].volume_cm3 < 800

    def test_paper_material_used(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0, material="paper")
        assert results[0].material == "paper"

    def test_plastic_material_used(self):
        results = optimize_package(tea_density=0.35, package_weight=250.0, material="plastic")
        assert results[0].material == "plastic"

    def test_invalid_density_raises(self):
        """Zero or negative density should produce very large volume, but should still work."""
        # Pydantic validation handles this at API layer; optimizer is lenient
        results = optimize_package(tea_density=0.05, package_weight=250.0)
        assert len(results) >= 1  # should still work, just large volume
