"""Environment-based application configuration from spec.md section 17."""

from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime settings for the GridWise LLM service."""

    gemini_api_key: str
    gemini_model: str
    gemini_base_url: str
    llm_timeout_seconds: float
    port: int
    log_level: str


def _optional_text(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return value


def _valid_port(default: int) -> int:
    raw_value = os.getenv("PORT", "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("PORT must be an integer.") from exc
    if not 1 <= value <= 65535:
        raise RuntimeError("PORT must be between 1 and 65535.")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load local .env values and return validated settings."""

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is required. Set it in the environment or a local .env file."
        )

    return Settings(
        gemini_api_key=api_key,
        gemini_model=_optional_text("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        gemini_base_url=_optional_text(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        ),
        llm_timeout_seconds=_positive_float("LLM_TIMEOUT_SECONDS", 20.0),
        port=_valid_port(8000),
        log_level=_optional_text("LOG_LEVEL", "INFO").upper(),
    )
