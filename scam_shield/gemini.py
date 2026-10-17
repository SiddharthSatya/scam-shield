"""Gemini client on Vertex AI."""

from google import genai
from google.genai import types

from scam_shield.settings import Settings

DEFAULT_TIMEOUT_MS = 30_000


def get_client(settings: Settings, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> genai.Client:
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project,
        location=settings.gcp_region,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )
