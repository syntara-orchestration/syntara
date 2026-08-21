"""Diagnostic script to verify sandbox capabilities inside a container.

Run this inside the actual Syntara worker container to determine which
sandbox tier is available before deploying the script node isolation fix.
Must be run as the worker UID (1001), not root.

Usage:
    python3 tools/test_sandbox_capabilities.py

    # Inside a running container:
    podman exec <container> python3 /opt/app-root/src/tools/test_sandbox_capabilities.py

    # Against the built image (as UID 1001, not root):
    podman run --rm --user 1001 syntara:latest python3 tools/test_sandbox_capabilities.py
"""

import ctypes
import ctypes.util
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PASS = "PASS"  # noqa: S105
FAIL = "FAIL"
SKIP = "SKIP"

# Must match build_pivot_root_command in script_sandbox.py
_UNSHARE_FLAGS = [
    "--user",
    "--map-root-user",
    "--mount",
    "--pid",
    "--fork",
    "--kill-child",
]


def _print_result(label: str, status: str, detail: str = "") -> None:
    """Print a check result with pass/fail/skip marker."""
    marker = {"PASS": "+", "FAIL": "-", "SKIP": "?"}[status]
    msg = f"  [{marker}] {label}"
    if detail:
        msg += f" -- {detail}"
    print(msg)


def check_kernel_version() -> None:
    """Report kernel version and whether it meets the Landlock minimum."""
    print("\n== Kernel ==")
    release = platform.release()
    _print_result("Version", PASS, release)

    major, minor = 0, 0
    parts = release.split(".")
    if len(parts) >= 2:  # noqa: PLR2004
        try:
            major = int(parts[0])
            minor = int(parts[1])
        except ValueError:
            pass

    if major > 5 or (major == 5 and minor >= 13):  # noqa: PLR2004
        _print_result("Landlock capable (>= 5.13)", PASS)
    else:
        _print_result("Landlock capable (>= 5.13)", FAIL, f"kernel {major}.{minor} < 5.13")


def check_landlock() -> tuple[str, int]:  # noqa: PLR0911
    """Probe Landlock ABI version via syscall."""
    print("\n== Tier 1: Landlock LSM ==")

    libc_name = ctypes.util.find_library("c")
    if not libc_name:
        _print_result("libc available", FAIL, "ctypes.util.find_library('c') returned None")
        return FAIL, -1

    try:
        libc = ctypes.CDLL(libc_name, use_errno=True)
        libc.syscall.restype = ctypes.c_long
    except OSError as e:
        _print_result("libc loadable", FAIL, str(e))
        return FAIL, -1

    _print_result("libc available", PASS, libc_name)

    arch = platform.machine()
    if arch in ("x86_64", "aarch64"):
        nr_create = 444
    else:
        _print_result("Architecture supported", FAIL, f"unknown syscall numbers for {arch}")
        return FAIL, -1

    _print_result("Architecture", PASS, arch)

    result = libc.syscall(nr_create, 0, 0, 1)
    errno_val = ctypes.get_errno()

    if result >= 1:
        _print_result("landlock_create_ruleset", PASS, f"ABI version {result}")
        return PASS, result
    if errno_val == 38:  # noqa: PLR2004
        _print_result("landlock_create_ruleset", FAIL, "ENOSYS -- kernel compiled without Landlock")
        return FAIL, -1
    if errno_val == 95:  # noqa: PLR2004
        _print_result("landlock_create_ruleset", FAIL, "EOPNOTSUPP -- Landlock disabled at boot")
        return FAIL, -1
    _print_result("landlock_create_ruleset", FAIL, f"returned {result}, errno={errno_val}")
    return FAIL, -1


def check_unshare_binary() -> str:
    """Check if unshare(1) is installed."""
    print("\n== Tier 2: User Namespace + Mount Namespace ==")

    unshare_path = shutil.which("unshare")
    if not unshare_path:
        _print_result("unshare binary", FAIL, "not found on PATH")
        return FAIL

    _print_result("unshare binary", PASS, unshare_path)
    return PASS


def check_unshare_userns() -> str:
    """Probe unshare with production flags."""
    try:
        result = subprocess.run(  # noqa: S603
            ["unshare", *_UNSHARE_FLAGS, "bash", "-c", "mount --make-rprivate /"],  # noqa: S607
            check=False,
            capture_output=True,
            timeout=5,
        )
        label = f"unshare {' '.join(_UNSHARE_FLAGS)}"
        if result.returncode == 0:
            _print_result(label, PASS)
            return PASS
        stderr = result.stderr.decode(errors="replace").strip()
        _print_result(label, FAIL, stderr)
        return FAIL
    except FileNotFoundError:
        _print_result("unshare probe", SKIP, "unshare not installed")
        return SKIP
    except Exception as e:  # noqa: BLE001
        _print_result("unshare probe", FAIL, str(e))
        return FAIL


def _production_wrapper(sandbox_dir: str, inner_script: str) -> str:
    """Build a shell script matching production build_pivot_root_command."""
    return (
        "set -e; "
        "mount --make-rprivate /; "
        "NEWROOT=$(mktemp -d); "
        "mount -t tmpfs tmpfs $NEWROOT; "
        # Bind /usr only
        "mkdir -p $NEWROOT/usr; "
        "mount --bind /usr $NEWROOT/usr; "
        # Symlinks for RHEL compat
        "ln -sf usr/lib $NEWROOT/lib 2>/dev/null || true; "
        "ln -sf usr/lib64 $NEWROOT/lib64 2>/dev/null || true; "
        "ln -sf usr/bin $NEWROOT/bin 2>/dev/null || true; "
        "ln -sf usr/sbin $NEWROOT/sbin 2>/dev/null || true; "
        # Individual /dev nodes
        "mkdir -p $NEWROOT/dev; "
        "touch $NEWROOT/dev/null; mount --bind /dev/null $NEWROOT/dev/null; "
        "touch $NEWROOT/dev/urandom; mount --bind /dev/urandom $NEWROOT/dev/urandom; "
        # Fresh procfs (may fail)
        "mkdir -p $NEWROOT/proc; "
        "mount -t proc proc $NEWROOT/proc 2>/dev/null || true; "
        # Private /tmp and sandbox dir
        "mkdir -p $NEWROOT/tmp; chmod 1777 $NEWROOT/tmp; "
        f"mkdir -p $NEWROOT{sandbox_dir}; "
        # Pivot root
        "mkdir -p $NEWROOT/old; "
        "pivot_root $NEWROOT $NEWROOT/old; "
        f"cd {sandbox_dir}; "
        # Detach old root: umount first, tmpfs overlay as fallback
        "if umount -l /old 2>/dev/null; then "
        "rmdir /old 2>/dev/null || true; "
        "else mount -t tmpfs tmpfs /old || exit 1; fi; "
        # chmod sandbox for nested userns
        f"chmod 1777 {sandbox_dir}; "
        "chmod 1777 /tmp 2>/dev/null || true; "
        # Drop privileges via nested userns, then run inner script
        f"exec unshare --user -- bash -c {_shell_quote(inner_script)}"
    )


def _shell_quote(s: str) -> str:
    """Single-quote a string for safe shell embedding."""
    return "'" + s.replace("'", "'\\''") + "'"


def check_pivot_root() -> str:
    """Test the full production wrapper: pivot_root, /old detach, nested unshare."""
    try:
        sandbox_dir = "/tmp/diag-sandbox"  # noqa: S108
        script = _production_wrapper(sandbox_dir, "echo pivot_root_ok")
        result = subprocess.run(  # noqa: S603
            ["unshare", *_UNSHARE_FLAGS, "bash", "-c", script],  # noqa: S607
            check=False,
            capture_output=True,
            timeout=10,
        )
        stdout = result.stdout.decode(errors="replace").strip()
        if result.returncode == 0 and "pivot_root_ok" in stdout:
            _print_result("pivot_root with production layout", PASS)
            return PASS
        stderr = result.stderr.decode(errors="replace").strip()
        _print_result("pivot_root with production layout", FAIL, stderr)
        return FAIL
    except Exception as e:  # noqa: BLE001
        _print_result("pivot_root with production layout", FAIL, str(e))
        return FAIL


def check_write_in_sandbox() -> str:
    """Verify scripts can write to the sandbox dir after nested unshare."""
    try:
        sandbox_dir = "/tmp/diag-sandbox"  # noqa: S108
        inner = "echo test_content > ./test_file.txt && cat ./test_file.txt && rm ./test_file.txt && echo write_ok"
        script = _production_wrapper(sandbox_dir, inner)
        result = subprocess.run(  # noqa: S603
            ["unshare", *_UNSHARE_FLAGS, "bash", "-c", script],  # noqa: S607
            check=False,
            capture_output=True,
            timeout=10,
        )
        stdout = result.stdout.decode(errors="replace").strip()
        if "write_ok" in stdout:
            _print_result("Write to sandbox dir (nested userns)", PASS)
            return PASS
        stderr = result.stderr.decode(errors="replace").strip()
        _print_result("Write to sandbox dir (nested userns)", FAIL, stderr)
        return FAIL
    except Exception as e:  # noqa: BLE001
        _print_result("Write to sandbox dir (nested userns)", FAIL, str(e))
        return FAIL


def check_secret_isolation() -> str:
    """Verify secrets are blocked after pivot_root (production layout)."""
    print("\n== Isolation Smoke Test ==")
    try:
        secret_dir = tempfile.mkdtemp(dir=str(Path.cwd()), prefix=".sandbox-test-")
        secret_file = str(Path(secret_dir) / "test-secret.pem")
        Path(secret_file).write_text("FAKE_SECRET_FOR_TESTING")

        sandbox_dir = "/tmp/diag-sandbox"  # noqa: S108
        inner = f"cat {secret_file} 2>&1 || echo SECRET_BLOCKED"
        script = _production_wrapper(sandbox_dir, inner)
        result = subprocess.run(  # noqa: S603
            ["unshare", *_UNSHARE_FLAGS, "bash", "-c", script],  # noqa: S607
            check=False,
            capture_output=True,
            timeout=10,
        )
        stdout = result.stdout.decode(errors="replace").strip()

        if "FAKE_SECRET_FOR_TESTING" in stdout:
            _print_result("Secret file blocked", FAIL, "secret was readable")
            return FAIL
        if "SECRET_BLOCKED" in stdout or "No such file" in stdout:
            _print_result("Secret file blocked", PASS, "file not accessible")
            return PASS
        _print_result("Secret file blocked", FAIL, f"unexpected: {stdout[:100]}")
        return FAIL
    except Exception as e:  # noqa: BLE001
        _print_result("Secret file blocked", FAIL, str(e))
        return FAIL
    finally:
        shutil.rmtree(secret_dir, ignore_errors=True)


def check_umount_old() -> str:
    """Verify scripts cannot umount /old to reveal the original root."""
    try:
        sandbox_dir = "/tmp/diag-sandbox"  # noqa: S108
        inner = "umount /old 2>/dev/null; cat /old/etc/hostname 2>/dev/null && echo OLD_LEAKED || echo OLD_SAFE"
        script = _production_wrapper(sandbox_dir, inner)
        result = subprocess.run(  # noqa: S603
            ["unshare", *_UNSHARE_FLAGS, "bash", "-c", script],  # noqa: S607
            check=False,
            capture_output=True,
            timeout=10,
        )
        stdout = result.stdout.decode(errors="replace").strip()
        if "OLD_SAFE" in stdout:
            _print_result("Script cannot reveal /old", PASS)
            return PASS
        if "OLD_LEAKED" in stdout:
            _print_result("Script cannot reveal /old", FAIL, "host files readable after umount")
            return FAIL
        _print_result("Script cannot reveal /old", FAIL, f"unexpected: {stdout[:100]}")
        return FAIL
    except Exception as e:  # noqa: BLE001
        _print_result("Script cannot reveal /old", FAIL, str(e))
        return FAIL


def main() -> None:
    """Run all capability checks and report which sandbox tier would be active."""
    print("=" * 60)
    print("Script Node Sandbox Capability Diagnostic")
    print(f"Python: {sys.executable} ({platform.python_version()})")
    print(f"PID: {os.getpid()} | UID: {os.getuid()} | GID: {os.getgid()}")
    print("=" * 60)

    check_kernel_version()

    landlock_status, abi_version = check_landlock()

    unshare_bin = check_unshare_binary()

    unshare_userns = SKIP
    pivot = SKIP
    write = SKIP
    isolation = SKIP
    umount_old = SKIP

    if unshare_bin == PASS:
        unshare_userns = check_unshare_userns()

        if unshare_userns == PASS:
            pivot = check_pivot_root()

            if pivot == PASS:
                write = check_write_in_sandbox()
                isolation = check_secret_isolation()
                umount_old = check_umount_old()

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)

    if landlock_status == PASS:
        print(f"\n  Active tier: Landlock LSM (ABI v{abi_version})")
        print("  Filesystem isolation: kernel-enforced allowlist")
    elif pivot == PASS:
        print("\n  Active tier: User namespace + mount namespace (unshare)")
        print("  Filesystem isolation: pivot_root with bind-mount allowlist")
        results = {"write": write, "isolation": isolation, "umount_old": umount_old}
        for name, status in results.items():
            marker = "OK" if status == PASS else "FAILED"
            print(f"  {name}: {marker}")
    else:
        print("\n  Active tier: NONE — script execution will be REFUSED")
        print("  Install util-linux, enable user namespaces, or upgrade kernel")

    print()


if __name__ == "__main__":
    main()
