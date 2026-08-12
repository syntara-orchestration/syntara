"""AUDIT-1: System user workaround removal — codebase verification.

Static analysis tests that verify the system user workaround
(``create_service_token()``, ``system_user_id``, and the well-known
system user UUID) has been completely removed from the application source.

These are not runtime tests — they scan the ``src/`` tree to prevent
regressions that re-introduce the system user pattern.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_SRC_DIR = Path(__file__).resolve().parents[4] / "src"


def _grep(pattern: str, path: Path, extra_args: list[str] | None = None) -> list[str]:
    """Run grep and return matching lines (empty list if no matches)."""
    cmd = ["grep", "-rn", *(extra_args or []), pattern, str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    return [line for line in result.stdout.strip().splitlines() if line]


class TestAUDIT1SystemUserRemoval:
    """AUDIT-1: The system user workaround is fully removed from src/."""

    def test_no_create_service_token(self) -> None:
        """``create_service_token`` must not exist in application code."""
        matches = _grep("create_service_token", _SRC_DIR)
        assert not matches, "create_service_token references found in src/:\n" + "\n".join(f"  {m}" for m in matches)

    def test_no_system_user_id_variable(self) -> None:
        """``system_user_id`` must not exist in application code."""
        matches = _grep("system_user_id", _SRC_DIR)
        assert not matches, "system_user_id references found in src/:\n" + "\n".join(f"  {m}" for m in matches)

    def test_no_system_user_uuid(self) -> None:
        """The well-known system user UUID must not appear in application code."""
        matches = _grep("00000000-0000-0000-0000-000000000001", _SRC_DIR)
        assert not matches, "System user UUID found in src/:\n" + "\n".join(f"  {m}" for m in matches)

    def test_no_system_user_db_seed(self) -> None:
        """Database seed/migration scripts must not create a system user row."""
        seed_dir = _SRC_DIR / "syntara"
        matches = _grep("system.user", seed_dir, extra_args=["-i"])
        benign_patterns = ("PrincipalType.SYSTEM", "System/User Prompt", "system user")
        filtered = [m for m in matches if not any(bp.lower() in m.lower() for bp in benign_patterns)]
        assert not filtered, "System user seeding references found:\n" + "\n".join(f"  {m}" for m in filtered)

    def test_no_internal_bearer_token_minting(self) -> None:
        """Internal HTTP clients must not mint or attach Bearer tokens."""
        http_client_dir = _SRC_DIR / "syntara" / "core" / "tls"
        matches = _grep("Bearer", http_client_dir)
        assert not matches, "Bearer token usage found in internal TLS/HTTP client code:\n" + "\n".join(
            f"  {m}" for m in matches
        )
