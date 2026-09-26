"""EP worker configuration — reads from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


def to_asyncpg_url(database_url: str) -> str:
    """Return a PostgreSQL URL without a SQLAlchemy DBAPI driver suffix."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


class ScriptExecutorSettings(BaseSettings):
    """Script execution settings — no database connection required.

    Used directly by script_executor.py so it can be imported and tested
    without a database URL in the environment.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # Process cleanup timing
    script_cleanup_terminate_timeout: float = 1.0
    script_cleanup_kill_timeout: float = 0.5

    # Per-env-var size cap (bytes)
    max_env_var_length: int = 32768  # 32 KB

    # Temporal payload — must match the server-side blobSize.error in development-sql.yaml
    temporal_blob_size_error: int = 2_097_152  # 2 MB

    @computed_field  # type: ignore[prop-decorator]
    @property
    def temporal_payload_max_bytes(self) -> int:
        """90% of temporal_blob_size_error — headroom for JSON escaping and protobuf overhead."""
        return int(self.temporal_blob_size_error * 0.9)


class EPSettings(ScriptExecutorSettings):
    """Full settings for the execution-plane worker, including database."""

    # Database — accepts either APP_DATABASE_URL or DATABASE_URL
    database_url: str = Field(
        validation_alias=AliasChoices("APP_DATABASE_URL", "DATABASE_URL"),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_asyncpg(self) -> str:
        """asyncpg-compatible URL (strips the +asyncpg SQLAlchemy driver prefix)."""
        return to_asyncpg_url(self.database_url)


@lru_cache
def get_script_executor_settings() -> ScriptExecutorSettings:
    """Load and cache script executor settings from the environment."""
    return ScriptExecutorSettings()


@lru_cache
def get_ep_settings() -> EPSettings:
    """Load and cache execution-plane settings from the environment."""
    # BaseSettings loads the required database_url from the environment.
    return EPSettings()  # type: ignore[call-arg]
