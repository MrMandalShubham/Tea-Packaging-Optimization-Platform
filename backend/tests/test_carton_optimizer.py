"""
Tests for Stage 2: Carton Optimizer.
"""
import pytest
from app.optimizers.carton import optimize_carton, CartonResult, CartonOptimizer


class TestCartonOptimizer:
    def test_returns_carton_result(self):
        result = optimize_carton(
            package_length_mm=120, package_width_mm=95,
            package_height_mm=60, shipment_quantity=100000,
            package_weight_kg=0.25,
        )
        assert isinstance(result, CartonResult)

    def test_units_per_carton_positive(self):
        result = optimize_carton(120, 95, 60, 100000, 0.25)
        assert result.units_per_carton >= 1
        assert result.units_per_carton <= 100000  # not more than total

    def test_carton_weight_within_limit(self):
        result = optimize_carton(120, 95, 60, 100000, 0.25)
        assert result.carton_weight_kg <= 25.0, f"Weight {result.carton_weight_kg} exceeds 25kg limit"

    def test_board_grade_determined(self):
        result = optimize_carton(120, 95, 60, 100000, 0.25)
        assert result.board_grade in ("3-ply", "5-ply", "7-ply", "9-ply")
        assert result.board_thickness_mm > 0

    def test_inner_dimensions_positive(self):
        result = optimize_carton(120, 95, 60, 100000, 0.25)
        assert result.inner_length_mm > 0
        assert result.inner_width_mm > 0
        assert result.inner_height_mm > 0

    def test_outer_dimensions_larger_than_inner(self):
        result = optimize_carton(120, 95, 60, 100000, 0.25)
        assert result.outer_length_mm > result.inner_length_mm
        assert result.outer_width_mm > result.inner_width_mm
        assert result.outer_height_mm > result.inner_height_mm

    def test_more_units_for_light_packages(self):
        light = optimize_carton(80, 60, 40, 100000, 0.05)  # 50g pack
        heavy = optimize_carton(200, 150, 100, 100000, 1.0)  # 1kg pack
        assert light.units_per_carton > heavy.units_per_carton

    def test_single_unit_fallback(self):
        """With enormous packages, should fall back to 1 unit per carton."""
        result = optimize_carton(500, 500, 400, 100000, 20.0)
        assert result.units_per_carton >= 1

    def test_heavy_package_triggers_thick_board(self):
        result = optimize_carton(200, 150, 100, 100000, 2.0)  # 2kg per pack
        # Heavier cartons → thicker board
        assert result.board_grade in ("5-ply", "7-ply", "9-ply")

    def test_arrangement_valid(self):
        result = optimize_carton(120, 95, 60, 100000, 0.25)
        nx, ny, nz = result.arrangement
        assert nx >= 1 and ny >= 1 and nz >= 1
        assert nx * ny * nz == result.units_per_carton


class TestCartonOptimizerClass:
    def test_optimizer_instantiation(self):
        opt = CartonOptimizer(
            package_length_mm=120, package_width_mm=95,
            package_height_mm=60, package_weight_g=250.0,
            shipment_quantity=100000,
        )
        result = opt.optimize()
        assert result.units_per_carton > 0

    def test_custom_max_weight(self):
        opt = CartonOptimizer(120, 95, 60, 250.0, 100000, max_carton_weight_kg=15.0)
        result = opt.optimize()
        assert result.carton_weight_kg <= 15.0
