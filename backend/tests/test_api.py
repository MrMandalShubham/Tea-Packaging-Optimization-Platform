"""
API endpoint tests using FastAPI TestClient.

Tests the stateless endpoints (optimize/*, compare, health).
Stateful endpoints (/simulation, /dashboard) require PostgreSQL.
"""
import pytest
from fastapi.testclient import TestClient


# Import happens at module level — may fail if DB not available
# We test only stateless endpoints
@pytest.fixture
def client():
    """Create TestClient, skip DB-dependent tests gracefully."""
    from app.main import app
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestPackageOptimization:
    def test_optimize_package_square(self, client):
        payload = {
            "tea_density": 0.35,
            "package_weight": 250.0,
            "package_shape": "square",
            "packaging_material": "paper",
        }
        response = client.post("/api/optimize/package", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "best_package" in data
        assert data["best_package"]["is_best"] is True
        assert data["best_package"]["volume_cm3"] > 0

    def test_optimize_package_round(self, client):
        payload = {
            "tea_density": 0.35,
            "package_weight": 250.0,
            "package_shape": "round",
            "packaging_material": "paper",
        }
        response = client.post("/api/optimize/package", json=payload)
        assert response.status_code == 200

    def test_optimize_package_plastic(self, client):
        payload = {
            "tea_density": 0.40,
            "package_weight": 500.0,
            "package_shape": "square",
            "packaging_material": "plastic",
        }
        response = client.post("/api/optimize/package", json=payload)
        assert response.status_code == 200

    def test_optimize_package_invalid_density(self, client):
        payload = {
            "tea_density": -0.1,  # invalid
            "package_weight": 250.0,
            "package_shape": "square",
            "packaging_material": "paper",
        }
        response = client.post("/api/optimize/package", json=payload)
        assert response.status_code == 422  # validation error


class TestCartonOptimization:
    def test_optimize_carton(self, client):
        payload = {
            "package_length_mm": 120,
            "package_width_mm": 95,
            "package_height_mm": 60,
            "package_weight_g": 250.0,
            "shipment_quantity": 100000,
        }
        response = client.post("/api/optimize/carton", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert data["config"]["units_per_carton"] > 0


class TestPalletOptimization:
    def test_optimize_pallet(self, client):
        payload = {
            "carton_length_mm": 380,
            "carton_width_mm": 290,
            "carton_height_mm": 250,
            "carton_weight_kg": 18.0,
        }
        response = client.post("/api/optimize/pallet", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["config"]["cartons_per_pallet"] > 0


class TestContainerOptimization:
    def test_optimize_container(self, client):
        payload = {
            "carton_length_mm": 380,
            "carton_width_mm": 290,
            "carton_height_mm": 250,
            "cartons_per_pallet": 48,
            "pallet_height_m": 1.2,
            "shipment_quantity": 100000,
            "units_per_carton": 24,
        }
        response = client.post("/api/optimize/container", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "best_container" in data
        assert data["best_container"]["is_best"] is True


class TestCompare:
    def test_compare_endpoint(self, client):
        payload = {
            "ship_quantity": 100000,
            "tea_density": 0.35,
            "package_weight": 250.0,
        }
        response = client.post("/api/compare", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert len(data["rows"]) >= 6
        assert data["total_savings"] > 0


class TestDocs:
    def test_swagger_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self, client):
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_json(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        # Verify all expected endpoints
        paths = list(data["paths"].keys())
        assert "/api/simulation" in paths
        assert "/api/simulation/{simulation_id}" in paths
        assert "/api/dashboard" in paths
        assert "/api/optimize/package" in paths
        assert "/api/compare" in paths
        assert "/health" in paths
