"""Runtime configuration, loaded from environment variables / `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    plaid_client_id: str = ""
    plaid_secret: SecretStr = SecretStr("")
    plaid_env: Literal["sandbox", "production"] = "sandbox"

    database_url: str = "sqlite:///data/finance.db"

    # Fernet key used to encrypt Plaid access tokens at rest. Generate with `finance gen-key`.
    finance_encryption_key: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
