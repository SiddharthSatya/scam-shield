"""UI config from env vars or the local .env file."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class UISettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    scam_shield_url: str = "http://localhost:8080"
    api_key: SecretStr
    # When the API is IAM-private, also send a Google ID token for the API URL.
    use_id_token: bool = False

    gcp_project: str
    gcp_region: str = "us-central1"
    bq_dataset: str = "scam_shield"

    def table(self, name: str) -> str:
        return f"`{self.gcp_project}.{self.bq_dataset}.{name}`"


@lru_cache
def get_ui_settings() -> UISettings:
    return UISettings()
