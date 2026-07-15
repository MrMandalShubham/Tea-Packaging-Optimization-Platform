"""
Tests for Stage 3: Pallet Optimizer.
"""
import pytest
from app.optimizers.pallet import optimize_pallet, PalletResult


class TestPalletOptimizer:
    def test_returns_pallet_result(self):
        result = optimize_pallet(380, 290, 250, 18.0)
        assert isinstance(result, PalletResult)

    def test_cartons_per_pallet_positive(self):
        result = optimize_pallet(380, 290, 250, 18.0)
        assert result.cartons_per_pallet >= 1

    def test_pallet_height_within_limit(self):
        result = optimize_pallet(380, 290, 250, 18.0)
        assert result.pallet_height_m <= 1.80, f"Pallet height {result.pallet_height_m}m exceeds 1.8m"

    def test_total_weight_within_limit(self):
        result = optimize_pallet(380, 290, 250, 18.0)
        assert result.total_weight_kg <= 1000.0, f"Weight {result.total_weight_kg} exceeds 1000kg"

    def test_cartons_per_pallet_equals_layer_times_layers(self):
        result = optimize_pallet(380, 290, 250, 18.0)
        assert result.cartons_per_pallet == result.cartons_per_layer * result.layers

    def test_small_cartons_fit_more(self):
        small = optimize_pallet(200, 150, 100, 5.0)
        large = optimize_pallet(600, 500, 400, 24.0)
        assert small.cartons_per_pallet > large.cartons_per_pallet

    def test_orientation_selected(self):
        result = optimize_pallet(380, 290, 250, 18.0)
        assert result.orientation in ("lengthwise", "widthwise", "single")

    def test_heavy_cartons_limit_layers(self):
        light = optimize_pallet(380, 290, 250, 5.0)
        heavy = optimize_pallet(380, 290, 250, 24.0)
        # Heavy cartons → fewer layers due to weight limit
        assert heavy.total_weight_kg <= 1000.0
        # Heavy may have same or fewer layers
        assert heavy.layers <= light.layers

    def test_edge_case_tiny_carton(self):
        result = optimize_pallet(100, 80, 50, 0.5)
        assert result.cartons_per_pallet > 0
        assert result.pallet_height_m <= 1.80

    def test_edge_case_oversized_carton(self):
        """Carton larger than pallet should still get 1 per layer."""
        result = optimize_pallet(1300, 1100, 500, 24.0)
        assert result.cartons_per_layer >= 1
