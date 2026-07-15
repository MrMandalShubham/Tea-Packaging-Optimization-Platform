from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Tea Packaging Optimization Platform"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://tea_user:tea_pass@localhost:5432/tea_packaging"
    database_url_sync: str = "postgresql://tea_user:tea_pass@localhost:5432/tea_packaging"

    secret_key: str = "change-me-in-production"

    # Container interior dimensions (meters) — ISO standard
    container_20gp_l: float = 5.90
    container_20gp_w: float = 2.35
    container_20gp_h: float = 2.39
    container_40gp_l: float = 12.04
    container_40gp_w: float = 2.35
    container_40gp_h: float = 2.39
    container_40hc_l: float = 12.04
    container_40hc_w: float = 2.35
    container_40hc_h: float = 2.70

    # Pallet dimensions (meters) — EUR/ISO standard
    pallet_l: float = 1.200
    pallet_w: float = 1.000
    pallet_h: float = 0.150
    pallet_max_load_kg: float = 1000.0

    # Optimization constraints
    max_carton_weight_kg: float = 25.0
    max_pallet_height_m: float = 1.80
    headspace_ratio: float = 0.15  # 15% extra volume for pouch fill

    # Cost defaults (INR)
    paper_cost_per_sqm: float = 12.0
    plastic_cost_per_sqm: float = 18.0
    metal_cost_per_sqm: float = 45.0
    freight_rate_per_nautical_mile: float = 2.5
    default_distance_nautical_miles: float = 5000.0

    # AI / OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
