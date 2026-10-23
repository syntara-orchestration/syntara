"""Contract tests for the development secret bootstrap script."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
_SOURCE_SCRIPT = _BACKEND / "tools" / "generate_secrets.sh"


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    project_root = tmp_path / "backend"
    tools = project_root / "tools"
    tools.mkdir(parents=True)
    script = tools / "generate_secrets.sh"
    shutil.copy2(_SOURCE_SCRIPT, script)
    script.chmod(0o755)
    shutil.copy2(_BACKEND / "Makefile", project_root / "Makefile")

    secrets_dir = project_root / ".secrets"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "bash").symlink_to("/bin/bash")
    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'call\\n' >> \"$TEST_VALIDATION_CALLS\"\n"
        'if [[ ! -s "$APP_SECRET_ENCRYPTION_KEY_PATH" ]]; then\n'
        "  echo 'encryption key is missing before password validation' >&2\n"
        "  exit 1\n"
        "fi\n"
        'password="$(cat)"\n'
        'printf \'%s\' "$password" > "$TEST_VALIDATED_PASSWORD"\n'
        'if [[ "${TEST_EXPECT_ADMIN_ABSENT:-0}" == 1 && -e "$TEST_ADMIN_PASSWORD_PATH" ]]; then\n'
        "  echo 'admin password was written before validation completed' >&2\n"
        "  exit 1\n"
        "fi\n"
        'printf \'%s\' "$password" | "$TEST_PYTHON" -c "$4"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)

    environment = os.environ.copy()
    environment.pop("APP_SECRET_ENCRYPTION_KEY", None)
    environment["APP_SECRET_ENCRYPTION_KEY_PATH"] = str(secrets_dir / "encryption-key")
    environment["APP_ADMIN_PASSWORD_PATH"] = str(secrets_dir / "admin-password")
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_BACKEND / "src"), environment.get("PYTHONPATH")]))
    environment["PATH"] = os.pathsep.join([str(bin_dir), environment["PATH"]])
    environment["TEST_SECRETS_DIR"] = str(secrets_dir)
    environment["TEST_ADMIN_PASSWORD_PATH"] = str(secrets_dir / "admin-password")
    environment["TEST_VALIDATION_CALLS"] = str(tmp_path / "validation-calls")
    environment["TEST_VALIDATED_PASSWORD"] = str(tmp_path / "validated-password")
    environment["TEST_PYTHON"] = sys.executable
    environment["TEST_EXPECT_ADMIN_ABSENT"] = "1"
    return script, secrets_dir, environment


def _run(script: Path, environment: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- executes an isolated fixture command
        ["make", "secrets-generate-force" if args == ("--force",) else "_ensure-secrets"],  # noqa: S607 -- uses the fixture's PATH
        cwd=script.parent.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_fresh_setup_creates_key_before_validating_and_atomically_writes_password(
    tmp_path: Path,
) -> None:
    script, secrets_dir, environment = _fixture(tmp_path)

    result = _run(script, environment)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    encryption_key = (secrets_dir / "encryption-key").read_text(encoding="utf-8").strip()
    assert len(encryption_key) == 64
    assert len((tmp_path / "validation-calls").read_text(encoding="utf-8").splitlines()) == 1
    assert (secrets_dir / "admin-password").read_bytes() == (tmp_path / "validated-password").read_bytes()
    assert not list(secrets_dir.glob(".admin-password.*"))


def test_invalid_explicit_password_preserves_existing_password_file(tmp_path: Path) -> None:
    script, secrets_dir, environment = _fixture(tmp_path)
    secrets_dir.mkdir(mode=0o700)
    (secrets_dir / "encryption-key").write_text("a" * 64, encoding="utf-8")
    existing_password = b"previous-valid-password"
    (secrets_dir / "admin-password").write_bytes(existing_password)
    environment["TEST_EXPECT_ADMIN_ABSENT"] = "0"
    environment["APP_ADMIN_PASSWORD"] = "weak"  # noqa: S105 -- intentionally invalid test value

    result = _run(script, environment, "--force")

    assert result.returncode != 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (secrets_dir / "admin-password").read_bytes() == existing_password
    assert not list(secrets_dir.glob(".admin-password.*"))


def test_valid_existing_encryption_key_is_preserved(tmp_path: Path) -> None:
    script, secrets_dir, environment = _fixture(tmp_path)
    secrets_dir.mkdir(mode=0o700)
    existing_key = "a" * 64
    (secrets_dir / "encryption-key").write_text(existing_key, encoding="utf-8")

    result = _run(script, environment)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (secrets_dir / "encryption-key").read_text(encoding="utf-8") == existing_key
    assert (secrets_dir / "admin-password").exists()


def test_empty_existing_encryption_key_is_replaced_before_password_validation(
    tmp_path: Path,
) -> None:
    script, secrets_dir, environment = _fixture(tmp_path)
    secrets_dir.mkdir(mode=0o700)
    (secrets_dir / "encryption-key").touch()

    result = _run(script, environment)

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    encryption_key = (secrets_dir / "encryption-key").read_text(encoding="utf-8").strip()
    assert len(encryption_key) == 64
    assert len((tmp_path / "validation-calls").read_text(encoding="utf-8").splitlines()) == 1
    assert (secrets_dir / "admin-password").read_bytes() == (tmp_path / "validated-password").read_bytes()
