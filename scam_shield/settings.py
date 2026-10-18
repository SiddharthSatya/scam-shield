"""All runtime config in one place. Values come from env vars or a local .env file."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gcp_project: str
    gcp_region: str = "us-central1"
    bq_dataset: str = "scam_shield"
    # flash-lite: 10/10 valid replies in Hindi/Marathi at ~1.2 s; 2.5-flash (no thinking)
    # looped on non-English output 7/10 times. See HANDOVER.md "Gotchas".
    gemini_model: str = "gemini-2.5-flash-lite"

    # Decision thresholds (see CONFIG.md for why these values).
    ask_threshold: float = 0.40  # money score at which we ask for context
    hold_threshold: float = 0.70  # combined score at which we hold the payment
    cooling_off_threshold: float = 0.90  # money score alone that triggers a cooling-off
    context_hold_threshold: float = 0.85  # context score alone that triggers a hold

    # Security. Both must be set; never commit real values.
    api_key: SecretStr  # shared with the bank backend, sent as X-API-Key
    token_secret: SecretStr  # signs the check token between /check-payment and /context
    # Covers safety check -> warning -> outcome while a person reads and taps.
    # Replay is blocked separately: /context is single-use per check (see service.py).
    token_ttl_seconds: int = 600

    def table(self, name: str) -> str:
        """Fully qualified BigQuery table id, e.g. project.dataset.table."""
        return f"{self.gcp_project}.{self.bq_dataset}.{name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
