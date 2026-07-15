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
