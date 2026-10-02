"""Tests for register_kind_sa_target."""

from __future__ import annotations

from typing import TYPE_CHECKING

import register_kind_sa_target
from dev_cli import DEFAULT_DATABASE_URL, EnvironmentProvider

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from dev_cli import EnvironmentDetails

_DB_ENV_VARS = (
    "APP_DATABASE_URL",
    "DATABASE_URL",
    "APP_DB_USER",
    "APP_DB_PASSWORD",
    "APP_DB_HOST",
    "APP_DB_PORT",
    "APP_DB_NAME",
)


def _clear_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _DB_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


def test_register_kind_sa_target_reads_token_and_registers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_database_env(monkeypatch)
    token_file = tmp_path / "sa-token.txt"
    token_file.write_text("sa-token-value\n", encoding="utf-8")
    registered: list[tuple[EnvironmentDetails, str]] = []

    async def _fake_register(details: EnvironmentDetails, database_url: str) -> None:
        registered.append((details, database_url))

    monkeypatch.setattr(register_kind_sa_target, "_register_environment_record", _fake_register)

    assert register_kind_sa_target.main([str(token_file)]) == 0

    details, database_url = registered[0]
    assert details.provider is EnvironmentProvider.KIND
    assert details.name == "execution-plane"
    assert details.endpoint == "https://execution-plane-control-plane:6443"
    assert details.namespace == "execution-plane"
    assert details.api_key == "sa-token-value"
    assert details.labels == {"provider": "kind", "cluster": "execution-plane"}
    assert database_url == DEFAULT_DATABASE_URL


def test_register_kind_sa_target_builds_url_from_app_db_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("APP_DB_USER", "ao")
    monkeypatch.setenv("APP_DB_PASSWORD", "p@ss:word")
    monkeypatch.setenv("APP_DB_HOST", "ao-postgres")
    monkeypatch.setenv("APP_DB_PORT", "5432")
    monkeypatch.setenv("APP_DB_NAME", "orchestrator")
    token_file = tmp_path / "sa-token.txt"
    token_file.write_text("sa-token-value\n", encoding="utf-8")
    registered: list[tuple[EnvironmentDetails, str]] = []

    async def _fake_register(details: EnvironmentDetails, database_url: str) -> None:
        registered.append((details, database_url))

    monkeypatch.setattr(register_kind_sa_target, "_register_environment_record", _fake_register)

    assert register_kind_sa_target.main([str(token_file)]) == 0

    _, database_url = registered[0]
    assert database_url == "postgresql+asyncpg://ao:p%40ss%3Aword@ao-postgres:5432/orchestrator"


def test_register_kind_sa_target_rejects_an_empty_token_file(tmp_path: Path) -> None:
    token_file = tmp_path / "sa-token.txt"
    token_file.write_text("   \n", encoding="utf-8")

    assert register_kind_sa_target.main([str(token_file)]) == 1
