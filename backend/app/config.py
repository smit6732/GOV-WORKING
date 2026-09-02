import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://cctv:cctv_pass@localhost:5432/cctv_registry",
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12 hours

    data_dir: str = os.getenv("DATA_DIR", "/app/data")
    stations_csv: str = "police_stations_gujarat.csv"
    cameras_csv: str = "demo_cctv_cameras.csv"

    # Camera health / ageing thresholds
    expected_service_life_years: int = 7

    # Coverage / gap analysis
    default_coverage_radius_m: int = 300  # metres, approximate per-camera visual coverage

    cors_origins: list[str] = ["*"]

    class Config:
        env_file = ".env"


settings = Settings()
