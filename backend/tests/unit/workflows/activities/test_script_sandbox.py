"""Unit tests for tiered script sandbox filesystem isolation.

Regression tests for AAP-87783: Script nodes must not be able to read
host secrets (JWT signing keys, encryption keys, etc.) from the Temporal
worker's filesystem.

These tests require Linux (Landlock LSM and/or unshare are Linux-only).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import syntara.workflows.workflow_engine.activities.script_sandbox as sandbox_mod
from syntara.workflows.workflow_engine.activities.script_sandbox import (
    ALLOWED_PATHS,
    SANDBOX_PATH,
    _detect_landlock_abi,
    _detect_unshare_userns,
    _get_python_runtime_paths,
    _shell_quote,
    build_pivot_root_command,
    cleanup_sandbox,
    create_sandbox_context,
    resolve_python_executable,
    sandbox_preexec_fn,
    sanitize_env_for_sandbox,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Sandbox requires Linux")

# ---------------------------------------------------------------------------
# Tier detection
# ---------------------------------------------------------------------------


class TestLandlockDetection:
    """Test Landlock ABI detection via syscall probe."""

    def _reset_cache(self) -> None:
        sandbox_mod._cached_landlock_abi = None

    def test_returns_integer(self) -> None:
        """Detection returns an integer (positive ABI version or -1)."""
        self._reset_cache()
        try:
            abi = _detect_landlock_abi()
            assert isinstance(abi, int)
            assert abi >= -1
        finally:
            self._reset_cache()

    def test_returns_negative_when_libc_unavailable(self) -> None:
        self._reset_cache()
        try:
            with patch.object(sandbox_mod, "_get_libc", return_value=None):
                assert _detect_landlock_abi() == -1
        finally:
            self._reset_cache()

    def test_caches_result(self) -> None:
        self._reset_cache()
        try:
            first = _detect_landlock_abi()
            with patch.object(sandbox_mod, "_get_libc", return_value=None):
                # Should return cached result, not re-probe
                assert _detect_landlock_abi() == first
        finally:
            self._reset_cache()


class TestUnshareDetection:
    """Test unshare --user --mount capability detection."""

    def _reset_cache(self) -> None:
        sandbox_mod._cached_unshare_userns = None

    def test_returns_false_when_binary_missing(self) -> None:
        self._reset_cache()
        try:
            with patch.object(shutil, "which", return_value=None):
                assert _detect_unshare_userns() is False
        finally:
            self._reset_cache()

    def test_returns_false_when_unshare_fails(self) -> None:
        self._reset_cache()
        try:
            mock_result: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess(
                args=["unshare", "--user", "--mount", "--pid", "--fork", "bash", "-c", "mount --make-rprivate /"],
                returncode=1,
            )
            with (
                patch.object(shutil, "which", return_value="/usr/bin/unshare"),
                patch("syntara.workflows.workflow_engine.activities.script_sandbox._sp.run", return_value=mock_result),
            ):
                assert _detect_unshare_userns() is False
        finally:
            self._reset_cache()

    def test_returns_true_when_unshare_works(self) -> None:
        self._reset_cache()
        try:
            mock_result: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess(
                args=["unshare", "--user", "--mount", "--pid", "--fork", "bash", "-c", "mount --make-rprivate /"],
                returncode=0,
            )
            with (
                patch.object(shutil, "which", return_value="/usr/bin/unshare"),
                patch("syntara.workflows.workflow_engine.activities.script_sandbox._sp.run", return_value=mock_result),
            ):
                assert _detect_unshare_userns() is True
        finally:
            self._reset_cache()

    def test_caches_result(self) -> None:
        self._reset_cache()
        try:
            mock_result: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess(args=[], returncode=0)
            with (
                patch.object(shutil, "which", return_value="/usr/bin/unshare"),
                patch(
                    "syntara.workflows.workflow_engine.activities.script_sandbox._sp.run", return_value=mock_result
                ) as mock_run,
            ):
                _detect_unshare_userns()
                _detect_unshare_userns()
                mock_run.assert_called_once()
        finally:
            self._reset_cache()


# ---------------------------------------------------------------------------
# ABI version handling
# ---------------------------------------------------------------------------


class TestHandledAccessForAbi:
    """Test ABI-version-dependent bitmask computation."""

    def test_abi_v1_mask(self) -> None:
        from syntara.workflows.workflow_engine.activities.script_sandbox import (
            _ABI_V1_MASK,
            _handled_access_for_abi,
        )

        assert _handled_access_for_abi(1) == _ABI_V1_MASK

    def test_abi_v2_mask(self) -> None:
        from syntara.workflows.workflow_engine.activities.script_sandbox import (
            _ABI_V2_MASK,
            _handled_access_for_abi,
        )

        assert _handled_access_for_abi(2) == _ABI_V2_MASK

    def test_abi_v3_mask(self) -> None:
        from syntara.workflows.workflow_engine.activities.script_sandbox import (
            _ABI_V3_MASK,
            _handled_access_for_abi,
        )

        assert _handled_access_for_abi(3) == _ABI_V3_MASK

    def test_abi_v7_uses_v3_mask(self) -> None:
        """ABI versions above v3 still use the v3 filesystem mask."""
        from syntara.workflows.workflow_engine.activities.script_sandbox import (
            _ABI_V3_MASK,
            _handled_access_for_abi,
        )

        assert _handled_access_for_abi(7) == _ABI_V3_MASK


# ---------------------------------------------------------------------------
# Allowed paths
# ---------------------------------------------------------------------------


class TestAllowedPaths:
    """Test the allowlist constant."""

    def test_includes_usr(self) -> None:
        paths = [p for p, _ in ALLOWED_PATHS]
        assert "/usr" in paths

    def test_dev_is_traverse_only(self) -> None:
        """/dev parent is traverse-only; individual devices have specific access."""
        from syntara.workflows.workflow_engine.activities.script_sandbox import _TRAVERSE

        dev_entries = {p: a for p, a in ALLOWED_PATHS if p == "/dev"}
        assert dev_entries["/dev"] == _TRAVERSE

    def test_includes_dev_null(self) -> None:
        paths = [p for p, _ in ALLOWED_PATHS]
        assert "/dev/null" in paths

    def test_includes_proc(self) -> None:
        paths = [p for p, _ in ALLOWED_PATHS]
        assert "/proc" in paths

    def test_does_not_include_run_secrets(self) -> None:
        paths = [p for p, _ in ALLOWED_PATHS]
        assert "/run/secrets" not in paths
        assert "/run" not in paths

    def test_etc_is_traverse_only(self) -> None:
        """/etc parent directory is traverse-only (READ_DIR), not full read."""
        from syntara.workflows.workflow_engine.activities.script_sandbox import _TRAVERSE

        etc_entries = [(p, a) for p, a in ALLOWED_PATHS if p == "/etc"]
        assert len(etc_entries) == 1
        assert etc_entries[0][1] == _TRAVERSE

    def test_proc_is_traverse_only(self) -> None:
        """/proc parent is traverse-only; /proc/self has read access."""
        from syntara.workflows.workflow_engine.activities.script_sandbox import _READ_ONLY, _TRAVERSE

        proc_entries = {p: a for p, a in ALLOWED_PATHS if p.startswith("/proc")}
        assert proc_entries["/proc"] == _TRAVERSE
        assert proc_entries["/proc/self"] == _READ_ONLY

    def test_does_not_include_run_or_secret_paths(self) -> None:
        paths = [p for p, _ in ALLOWED_PATHS]
        assert "/run" not in paths
        assert "/run/secrets" not in paths
        assert "/etc/secrets" not in paths
        assert "/etc/automation-orchestrator/secrets" not in paths


# ---------------------------------------------------------------------------
# Environment and path helpers
# ---------------------------------------------------------------------------


class TestSanitizeEnvForSandbox:
    """Test PATH and TMPDIR sanitization."""

    def test_replaces_path(self) -> None:
        env = {"PATH": "/sandbox/.local/bin:/usr/bin", "HOME": "/tmp"}  # noqa: S108
        result = sanitize_env_for_sandbox(env, "/tmp/sandbox-123")  # noqa: S108
        assert result["PATH"] == SANDBOX_PATH
        assert "/sandbox" not in result["PATH"]

    def test_sets_tmpdir_to_sandbox(self) -> None:
        env = {"PATH": "/usr/bin"}
        result = sanitize_env_for_sandbox(env, "/tmp/sandbox-456")  # noqa: S108
        assert result["TMPDIR"] == "/tmp/sandbox-456"  # noqa: S108
        assert result["TMP"] == "/tmp/sandbox-456"  # noqa: S108
        assert result["TEMP"] == "/tmp/sandbox-456"  # noqa: S108

    def test_preserves_other_vars(self) -> None:
        env = {"PATH": "/something", "HOME": "/tmp", "LANG": "C"}  # noqa: S108
        result = sanitize_env_for_sandbox(env, "/tmp/sandbox-789")  # noqa: S108
        assert result["HOME"] == "/tmp"  # noqa: S108
        assert result["LANG"] == "C"

    def test_does_not_mutate_original(self) -> None:
        env = {"PATH": "/original"}
        sanitize_env_for_sandbox(env, "/tmp/sandbox-abc")  # noqa: S108
        assert env["PATH"] == "/original"
        assert "TMPDIR" not in env


class TestResolvePythonExecutable:
    """Test Python executable path resolution."""

    def test_returns_real_path(self) -> None:
        result = resolve_python_executable()
        assert Path(result).is_absolute()
        assert Path(result).exists()
        assert result == os.path.realpath(result)


class TestGetPythonRuntimePaths:
    """Test dynamic Python path detection."""

    def test_returns_list(self) -> None:
        """Returns a list (may be empty on macOS where Python is not under /usr)."""
        paths = _get_python_runtime_paths()
        assert isinstance(paths, list)

    def test_all_paths_are_absolute(self) -> None:
        for p in _get_python_runtime_paths():
            assert Path(p).is_absolute()

    def test_all_paths_are_resolved(self) -> None:
        for p in _get_python_runtime_paths():
            assert p == os.path.realpath(p)

    def test_all_paths_under_usr(self) -> None:
        """Venv paths (e.g. /opt/app-root/.venv) must be excluded."""
        for p in _get_python_runtime_paths():
            assert p.startswith("/usr"), f"Non-/usr path leaked: {p}"


class TestShellQuote:
    """Test shell quoting."""

    def test_simple_string(self) -> None:
        assert _shell_quote("hello") == "'hello'"

    def test_string_with_single_quotes(self) -> None:
        assert _shell_quote("it's") == "'it'\\''s'"

    def test_empty_string(self) -> None:
        assert _shell_quote("") == "''"


# ---------------------------------------------------------------------------
# Drop supplementary groups
# ---------------------------------------------------------------------------


class TestDropSupplementaryGroups:
    """Test supplementary group dropping."""

    def test_does_not_raise(self) -> None:
        """Must not raise even if setgroups fails (e.g. unprivileged)."""
        from syntara.workflows.workflow_engine.activities.script_sandbox import _drop_supplementary_groups

        _drop_supplementary_groups()

    def test_handles_permission_error(self) -> None:
        from syntara.workflows.workflow_engine.activities.script_sandbox import _drop_supplementary_groups

        with patch("os.setgroups", side_effect=PermissionError("not allowed")):
            _drop_supplementary_groups()


# ---------------------------------------------------------------------------
# Preexec function
# ---------------------------------------------------------------------------


class TestSandboxPreexecFn:
    """Test the preexec function applied to subprocess."""

    def test_changes_cwd_to_sandbox_dir(self) -> None:
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        try:
            original_cwd = str(Path.cwd())
            sandbox_preexec_fn(sandbox_dir)
            assert str(Path.cwd()) == sandbox_dir
            os.chdir(original_cwd)
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    def test_sets_restrictive_umask(self) -> None:
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        try:
            original_cwd = str(Path.cwd())
            original_umask = os.umask(0o022)
            os.umask(original_umask)
            sandbox_preexec_fn(sandbox_dir)
            current_umask = os.umask(original_umask)
            assert current_umask == 0o077
            os.chdir(original_cwd)
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    def test_handles_nonexistent_sandbox_dir(self) -> None:
        sandbox_preexec_fn("/nonexistent/sandbox/dir")

    def test_skips_landlock_when_not_requested(self) -> None:
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        try:
            original_cwd = str(Path.cwd())
            with patch.object(sandbox_mod, "_apply_landlock_sandbox") as mock_ll:
                sandbox_preexec_fn(sandbox_dir, apply_landlock=False)
                mock_ll.assert_not_called()
            os.chdir(original_cwd)
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    def test_calls_landlock_when_requested(self) -> None:
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        try:
            original_cwd = str(Path.cwd())
            with patch.object(sandbox_mod, "_apply_landlock_sandbox") as mock_ll:
                sandbox_preexec_fn(sandbox_dir, apply_landlock=True, abi_version=3)
                mock_ll.assert_called_once_with(sandbox_dir, 3, None)
            os.chdir(original_cwd)
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    def test_passes_extra_paths_to_landlock(self) -> None:
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        try:
            original_cwd = str(Path.cwd())
            with patch.object(sandbox_mod, "_apply_landlock_sandbox") as mock_ll:
                sandbox_preexec_fn(
                    sandbox_dir,
                    apply_landlock=True,
                    abi_version=3,
                    extra_allowed_paths=["/data"],
                )
                mock_ll.assert_called_once_with(sandbox_dir, 3, ["/data"])
            os.chdir(original_cwd)
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    def test_skips_landlock_when_abi_negative(self) -> None:
        """Landlock not applied when abi_version is -1 even if apply_landlock=True."""
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        try:
            original_cwd = str(Path.cwd())
            with patch.object(sandbox_mod, "_apply_landlock_sandbox") as mock_ll:
                sandbox_preexec_fn(sandbox_dir, apply_landlock=True, abi_version=-1)
                mock_ll.assert_not_called()
            os.chdir(original_cwd)
        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tier 2: pivot_root command building
# ---------------------------------------------------------------------------


class TestBuildPivotRootCommand:
    """Test unshare + bind-mount + pivot_root command wrapping."""

    def test_wraps_bash_command(self) -> None:
        sandbox_dir = "/tmp/test-sandbox"  # noqa: S108
        cmd = ["bash", "-c", "echo hello"]
        result = build_pivot_root_command(cmd, sandbox_dir)
        assert result[0] == "unshare"
        assert "--user" in result
        assert "--map-root-user" in result
        assert "--mount" in result
        assert "--pid" in result
        assert "--fork" in result
        assert "--kill-child" in result
        assert "pivot_root" in result[-1]
        assert "echo hello" in result[-1]

    def test_wraps_python_command(self) -> None:
        sandbox_dir = "/tmp/test-sandbox"  # noqa: S108
        cmd = ["/usr/bin/python3", "-c", "print('hello')"]
        result = build_pivot_root_command(cmd, sandbox_dir)
        assert result[0] == "unshare"
        assert "pivot_root" in result[-1]
        assert "print" in result[-1]

    def test_includes_make_rprivate(self) -> None:
        cmd = ["bash", "-c", "echo test"]
        result = build_pivot_root_command(cmd, "/tmp/sandbox")  # noqa: S108
        assert "make-rprivate" in result[-1]

    def test_includes_fresh_procfs(self) -> None:
        cmd = ["bash", "-c", "echo test"]
        result = build_pivot_root_command(cmd, "/tmp/sandbox")  # noqa: S108
        assert "mount -t proc proc" in result[-1]

    def test_masks_old_root_with_tmpfs(self) -> None:
        """Old root must be masked with tmpfs to prevent access to host secrets."""
        cmd = ["bash", "-c", "echo test"]
        result = build_pivot_root_command(cmd, "/tmp/sandbox")  # noqa: S108
        assert "mount -t tmpfs tmpfs /old" in result[-1]

    def test_bash_uses_exec_in_nested_userns(self) -> None:
        """Bash scripts must exec inside a nested unprivileged user namespace."""
        cmd = ["bash", "-c", "echo hello"]
        result = build_pivot_root_command(cmd, "/tmp/sandbox")  # noqa: S108
        assert "exec unshare --user -- bash -c" in result[-1]

    def test_creates_tmp_in_new_root(self) -> None:
        """New root must have /tmp for scripts that ignore TMPDIR."""
        cmd = ["bash", "-c", "echo test"]
        result = build_pivot_root_command(cmd, "/tmp/sandbox")  # noqa: S108
        assert "mkdir -p $NEWROOT/tmp" in result[-1]

    def test_chmod_1777_before_nested_unshare(self) -> None:
        """Sandbox dir must be world-writable before dropping to unprivileged userns."""
        cmd = ["bash", "-c", "echo test"]
        result = build_pivot_root_command(cmd, "/tmp/sandbox")  # noqa: S108
        assert "chmod 1777 '/tmp/sandbox'" in result[-1]

    def test_python_interpreter_is_quoted(self) -> None:
        """Python interpreter path must be shell-quoted in exec."""
        cmd = ["/usr/bin/python3", "-c", "print('hello')"]
        result = build_pivot_root_command(cmd, "/tmp/sandbox")  # noqa: S108
        assert "exec unshare --user -- '/usr/bin/python3'" in result[-1]


# ---------------------------------------------------------------------------
# Context creation
# ---------------------------------------------------------------------------


class TestCreateSandboxContext:
    """Test sandbox context creation and tier selection."""

    def test_creates_temp_directory(self) -> None:
        ctx = create_sandbox_context(sandbox_enabled=True)
        try:
            assert Path(ctx["sandbox_dir"]).is_dir()
            assert "script-sandbox-" in ctx["sandbox_dir"]
        finally:
            cleanup_sandbox(ctx["sandbox_dir"])

    def test_preexec_fn_callable(self) -> None:
        ctx = create_sandbox_context(sandbox_enabled=True)
        try:
            assert callable(ctx["preexec_fn"])
        finally:
            cleanup_sandbox(ctx["sandbox_dir"])

    def test_returns_tier_string(self) -> None:
        ctx = create_sandbox_context(sandbox_enabled=True)
        try:
            assert ctx["tier"] in ("landlock", "unshare", "baseline")
        finally:
            cleanup_sandbox(ctx["sandbox_dir"])

    def test_disabled_sandbox_returns_baseline(self) -> None:
        ctx = create_sandbox_context(sandbox_enabled=False)
        try:
            assert ctx["tier"] == "baseline"
        finally:
            cleanup_sandbox(ctx["sandbox_dir"])

    def test_selects_landlock_when_available(self) -> None:
        sandbox_mod._cached_landlock_abi = None
        try:
            with patch.object(sandbox_mod, "_detect_landlock_abi", return_value=3):
                ctx = create_sandbox_context(sandbox_enabled=True)
                try:
                    assert ctx["tier"] == "landlock"
                finally:
                    cleanup_sandbox(ctx["sandbox_dir"])
        finally:
            sandbox_mod._cached_landlock_abi = None

    def test_falls_back_to_unshare(self) -> None:
        sandbox_mod._cached_landlock_abi = None
        sandbox_mod._cached_unshare_userns = None
        try:
            with (
                patch.object(sandbox_mod, "_detect_landlock_abi", return_value=-1),
                patch.object(sandbox_mod, "_detect_unshare_userns", return_value=True),
            ):
                ctx = create_sandbox_context(sandbox_enabled=True)
                try:
                    assert ctx["tier"] == "unshare"
                finally:
                    cleanup_sandbox(ctx["sandbox_dir"])
        finally:
            sandbox_mod._cached_landlock_abi = None
            sandbox_mod._cached_unshare_userns = None

    def test_refuses_execution_when_no_tier_available(self) -> None:
        """When sandbox is enabled but no isolation tier works, refuse to run."""
        sandbox_mod._cached_landlock_abi = None
        sandbox_mod._cached_unshare_userns = None
        try:
            with (
                patch.object(sandbox_mod, "_detect_landlock_abi", return_value=-1),
                patch.object(sandbox_mod, "_detect_unshare_userns", return_value=False),
            ):
                with pytest.raises(RuntimeError, match="Script sandbox is enabled"):
                    create_sandbox_context(sandbox_enabled=True)
        finally:
            sandbox_mod._cached_landlock_abi = None
            sandbox_mod._cached_unshare_userns = None

    def test_disabled_sandbox_allows_baseline(self) -> None:
        """When sandbox is explicitly disabled, baseline is allowed."""
        sandbox_mod._cached_landlock_abi = None
        sandbox_mod._cached_unshare_userns = None
        try:
            with (
                patch.object(sandbox_mod, "_detect_landlock_abi", return_value=-1),
                patch.object(sandbox_mod, "_detect_unshare_userns", return_value=False),
            ):
                ctx = create_sandbox_context(sandbox_enabled=False)
                try:
                    assert ctx["tier"] == "baseline"
                finally:
                    cleanup_sandbox(ctx["sandbox_dir"])
        finally:
            sandbox_mod._cached_landlock_abi = None
            sandbox_mod._cached_unshare_userns = None

    def test_unshare_tier_passes_extra_allowed_paths(self) -> None:
        """extra_allowed_paths must be available in the unshare tier context."""
        sandbox_mod._cached_landlock_abi = None
        sandbox_mod._cached_unshare_userns = None
        try:
            with (
                patch.object(sandbox_mod, "_detect_landlock_abi", return_value=-1),
                patch.object(sandbox_mod, "_detect_unshare_userns", return_value=True),
            ):
                ctx = create_sandbox_context(
                    sandbox_enabled=True,
                    extra_allowed_paths=["/data/shared"],
                )
                try:
                    assert ctx["tier"] == "unshare"
                    assert ctx["extra_allowed_paths"] == ["/data/shared"]
                finally:
                    cleanup_sandbox(ctx["sandbox_dir"])
        finally:
            sandbox_mod._cached_landlock_abi = None
            sandbox_mod._cached_unshare_userns = None

    def test_rejects_root_as_extra_allowed_path(self) -> None:
        """/ as an extra allowed path must be rejected."""
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/"])

    def test_rejects_proc_as_extra_allowed_path(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/proc"])

    def test_rejects_run_as_extra_allowed_path(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/run"])

    def test_rejects_etc_secrets_by_prefix(self) -> None:
        """Subdirectories of denied prefixes must also be rejected."""
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/etc/secrets"])

    def test_rejects_run_secrets_by_prefix(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/run/secrets"])

    def test_rejects_dev_shm_by_prefix(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/dev/shm"])  # noqa: S108

    def test_rejects_tmp_by_prefix(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/tmp"])  # noqa: S108

    def test_rejects_var_by_prefix(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/var/run/secrets"])

    def test_rejects_opt_by_prefix(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/opt/app-root"])

    def test_rejects_sys_by_prefix(self) -> None:
        with pytest.raises(ValueError, match="undermine the sandbox"):
            create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/sys"])

    def test_accepts_safe_extra_allowed_path(self) -> None:
        ctx = create_sandbox_context(sandbox_enabled=True, extra_allowed_paths=["/data/shared"])
        cleanup_sandbox(ctx["sandbox_dir"])

    def test_extra_allowed_paths_in_pivot_root_command(self) -> None:
        """Extra allowed paths must appear as quoted bind-mounts in the pivot_root script."""
        extra_dir = tempfile.mkdtemp(prefix="test-extra-")
        try:
            cmd = ["bash", "-c", "echo test"]
            result = build_pivot_root_command(cmd, "/tmp/sandbox", [extra_dir])  # noqa: S108
            real_dir = os.path.realpath(extra_dir)
            quoted = f"'{real_dir}'"
            assert quoted in result[-1]
            assert f"mount --bind {quoted}" in result[-1]
        finally:
            shutil.rmtree(extra_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestCleanupSandbox:
    """Test sandbox cleanup."""

    def test_removes_temp_directory(self) -> None:
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        assert Path(sandbox_dir).exists()
        cleanup_sandbox(sandbox_dir)
        assert not Path(sandbox_dir).exists()

    def test_handles_already_removed(self) -> None:
        cleanup_sandbox("/nonexistent/sandbox/dir")

    def test_removes_files_inside_sandbox(self) -> None:
        sandbox_dir = tempfile.mkdtemp(prefix="test-sandbox-")
        Path(sandbox_dir, "test_file.txt").write_text("content")
        cleanup_sandbox(sandbox_dir)
        assert not Path(sandbox_dir).exists()
