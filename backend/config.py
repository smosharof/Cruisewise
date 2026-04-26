from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"
    port: int = 8082

    # GCP / Vertex AI — auth via Application Default Credentials, no key needed
    gcp_project: str = "ms7285-ieor4576-proj03"
    gcp_location: str = "us-central1"
    llm_model: str = "google/gemini-2.5-flash"

    # Database
    database_url: str = "postgresql://localhost/cruisewise"

    # CORS — comma-separated origins
    allowed_origins: str = "http://localhost:8082,http://localhost:3000"

    # Apify — cruise inventory scraping. Empty default lets local dev start
    # without the token (inventory refresh just won't run); production injects
    # the real value from Secret Manager via Cloud Run env mount.
    apify_api_token: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def configure_logging(self) -> None:
        fmt = (
            '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
            if self.is_production
            else "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
        )
        logging.basicConfig(level=logging.INFO, format=fmt)
        # Quiet noisy third-party loggers
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    # In production, secrets are injected as env vars from GCP Secret Manager at deploy time.
    # No runtime Secret Manager client is needed; Cloud Run handles injection.
    return settings
