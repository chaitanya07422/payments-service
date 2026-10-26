from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "0.0.0.0"
    port: int = 8100
    mongo_uri: str | None = None
    mongo_db: str = "payments"
    catalog_path: str = "config/products.yaml"

    polar_access_token: str | None = None
    polar_webhook_secret: str | None = None
    polar_environment: str = "sandbox"
    polar_success_url_default: str = "https://vulscan.duckdns.org/pricing?paid=1"

    admin_api_key: str | None = None
    allow_mock_provider: bool = True


def _load_dotenv() -> None:
    """Load .env into os.environ without overriding existing keys."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=False)


@lru_cache
def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        polar_access_token=os.getenv("POLAR_ACCESS_TOKEN") or None,
        polar_webhook_secret=os.getenv("POLAR_WEBHOOK_SECRET") or None,
        polar_environment=os.getenv("POLAR_ENVIRONMENT") or "sandbox",
        polar_success_url_default=os.getenv("POLAR_SUCCESS_URL_DEFAULT")
        or "https://vulscan.duckdns.org/pricing?paid=1",
        mongo_uri=os.getenv("PAYMENTS_MONGO_URI")
        or os.getenv("VULN_AGENT_MONGO_URI")
        or None,
        mongo_db=os.getenv("MONGO_DB") or "payments",
        admin_api_key=os.getenv("PAYMENTS_ADMIN_KEY") or None,
        allow_mock_provider=(
            os.getenv("ALLOW_MOCK_PROVIDER", "true").lower() in ("1", "true", "yes")
        ),
        host=os.getenv("HOST") or "0.0.0.0",
        port=int(os.getenv("PORT") or "8100"),
    )


def resolve_path(rel: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    p = Path(rel)
    if p.is_file():
        return p
    cand = root / rel
    if cand.is_file():
        return cand
    return Path.cwd() / rel
