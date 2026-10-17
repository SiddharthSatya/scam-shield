"""All runtime config in one place. Values come from env vars or a local .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gcp_project: str
    gcp_region: str = "us-central1"
    bq_dataset: str = "scam_shield"
    gemini_model: str = "gemini-2.5-flash"

    def table(self, name: str) -> str:
        """Fully qualified BigQuery table id, e.g. project.dataset.table."""
        return f"{self.gcp_project}.{self.bq_dataset}.{name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
