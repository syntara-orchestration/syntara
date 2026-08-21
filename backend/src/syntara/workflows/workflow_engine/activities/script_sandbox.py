"""Filesystem sandbox for script node execution.

Provides process-level isolation so user-supplied scripts cannot read
host secrets (JWT signing keys, encryption keys, database credentials)
from the Temporal worker's filesystem. Filesystem-only — network access
is not restricted.

Uses a tiered allowlist approach — only explicitly permitted paths are
accessible, everything else is blocked:

Tier 1: Landlock LSM (RHEL 10 default, RHEL 9 with Landlock-enabled kernels)
    Kernel-enforced per-process filesystem allowlist via syscalls.
    Applied in ``preexec_fn`` (child only). Scripts are stdlib-only
    (site-packages not on the allowlist by default).

Tier 2: User namespace + mount namespace (RHEL 9 fallback)
    ``unshare --user --map-root-user --mount --pid --fork --kill-child``
    with bind-mount allowlist and ``pivot_root``. The old root is detached
    (``umount -l``, tmpfs overlay as fallback). A nested ``unshare --user``
    (without ``--map-root-user``) drops ``CAP_SYS_ADMIN`` before exec so
    scripts cannot undo the overlay. ``chmod 1777`` on the sandbox dir
    and ``/tmp`` ensures the unprivileged nested user can still write.

If neither tier is available and ``script_sandbox_enabled`` is True,
script execution is refused (fail-closed).

Baseline preexec hardening (restricted CWD, PR_SET_NO_NEW_PRIVS,
dropped groups, restrictive umask) is always applied regardless of tier.
"""

import contextlib
import ctypes
import ctypes.util
import os
import shutil
import subprocess as _sp
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PR_SET_NO_NEW_PRIVS = 38  # prctl(2) option number

# Named Landlock ABI version thresholds (avoid magic numbers in comparisons)
_LANDLOCK_ABI_V2 = 2
_LANDLOCK_ABI_V3 = 3

# Landlock syscall numbers (same on x86_64 and aarch64)
_NR_LANDLOCK_CREATE_RULESET = 444
_NR_LANDLOCK_ADD_RULE = 445
_NR_LANDLOCK_RESTRICT_SELF = 446

LANDLOCK_CREATE_RULESET_VERSION = 1 << 0
LANDLOCK_RULE_PATH_BENEATH = 1

# Landlock filesystem access rights — defined for ABI completeness.
# Only a subset is referenced directly (EXECUTE, WRITE_FILE, READ_FILE,
# READ_DIR); the rest contribute implicitly via the _ABI_V*_MASK bitmasks.
LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0
LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3
LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4
LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
LANDLOCK_ACCESS_FS_MAKE_CHAR = 1 << 6
LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
LANDLOCK_ACCESS_FS_MAKE_SOCK = 1 << 9
LANDLOCK_ACCESS_FS_MAKE_FIFO = 1 << 10
LANDLOCK_ACCESS_FS_MAKE_BLOCK = 1 << 11
LANDLOCK_ACCESS_FS_MAKE_SYM = 1 << 12
LANDLOCK_ACCESS_FS_REFER = 1 << 13  # ABI v2, kernel 5.19+
LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14  # ABI v3, kernel 6.2+

# Cumulative bitmasks — all access rights available in each ABI version.
# Used as handled_access_fs to tell the kernel which rights to enforce.
_ABI_V1_MASK = (1 << 13) - 1
_ABI_V2_MASK = (1 << 14) - 1
_ABI_V3_MASK = (1 << 15) - 1

# Composite access masks for ALLOWED_PATHS rules
_READ_ONLY = LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR
_READ_EXECUTE = _READ_ONLY | LANDLOCK_ACCESS_FS_EXECUTE
_READ_WRITE = _READ_ONLY | LANDLOCK_ACCESS_FS_WRITE_FILE

# open(2) flags for Landlock path FD acquisition
O_PATH = 0o10000000
O_CLOEXEC = 0o2000000

# Landlock READ_DIR on parent directories enables traversal to children.
# Individual file rules use READ_FILE only (READ_DIR is invalid for files
# and causes EINVAL from the kernel).
_TRAVERSE = LANDLOCK_ACCESS_FS_READ_DIR

# Allowlist of paths scripts are permitted to access.
# Everything NOT on this list is blocked by both Tier 1 and Tier 2.
ALLOWED_PATHS: tuple[tuple[str, int], ...] = (
    # /usr — interpreters, libraries, runtime data (read + execute)
    ("/usr", _READ_EXECUTE),
    # Compat symlinks for non-RHEL systems where /bin != /usr/bin
    ("/bin", _READ_EXECUTE),
    ("/sbin", _READ_EXECUTE),
    ("/lib", _READ_ONLY),
    ("/lib64", _READ_ONLY),
    # /dev — traverse-only, individual devices below.
    # NOT all of /dev — /dev/shm is shared memory visible to other processes.
    ("/dev", _TRAVERSE),
    ("/dev/null", _READ_WRITE),
    ("/dev/urandom", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/dev/zero", LANDLOCK_ACCESS_FS_READ_FILE),
    # /proc — traverse only, then /proc/self gets read access.
    # This prevents scripts from reading /proc/<worker_pid>/environ
    # which would leak all worker secrets.
    ("/proc", _TRAVERSE),
    ("/proc/self", _READ_ONLY),
    # /etc — traverse only at top level, individual entries below.
    # NOT all of /etc — secrets may be mounted at /etc/secrets.
    ("/etc", _TRAVERSE),
    ("/etc/localtime", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/resolv.conf", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/hosts", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/nsswitch.conf", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/ld.so.cache", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/ld.so.conf", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/ld.so.conf.d", _READ_ONLY),
    ("/etc/ssl/certs", _READ_ONLY),
    ("/etc/ssl/cert.pem", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/pki/tls/certs", _READ_ONLY),
    ("/etc/pki/tls/cert.pem", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/pki/ca-trust", _READ_ONLY),
    ("/etc/alternatives", _READ_ONLY),
    ("/etc/bashrc", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/profile", LANDLOCK_ACCESS_FS_READ_FILE),
    ("/etc/profile.d", _READ_ONLY),
)

# Paths for Tier 2 bind-mount (directories only, resolved at build time).
# /tmp is NOT included — the new root is already a tmpfs, so scripts
# write to the tmpfs directly. Binding host /tmp would leak data between
# concurrent scripts and expose anything the worker left there.
_TIER2_BIND_DIRS: tuple[str, ...] = ("/usr",)

# Individual devices to bind-mount in Tier 2 (not all of /dev).
_TIER2_DEV_NODES: tuple[str, ...] = (
    "/dev/null",
    "/dev/urandom",
    "/dev/zero",
)

# cert.pem files are not listed here — they are symlinks that resolve
# into directories already bind-mounted (e.g. /etc/pki/ca-trust).
_TIER2_ETC_FILES: tuple[str, ...] = (
    "/etc/localtime",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/nsswitch.conf",
    "/etc/ld.so.cache",
    "/etc/ld.so.conf",
    "/etc/ld.so.conf.d",
    "/etc/ssl/certs",
    "/etc/pki/tls/certs",
    "/etc/pki/ca-trust",
    "/etc/alternatives",
    "/etc/bashrc",
    "/etc/profile",
    "/etc/profile.d",
)
# NOTE: Both tiers restrict /etc to individual files/dirs. Tier 2
# bind-mounts them; Tier 1 uses traverse-only on /etc with per-file
# READ_FILE rules. Secrets under /etc/secrets are not allowlisted.

# ---------------------------------------------------------------------------
# Landlock ctypes structs
# ---------------------------------------------------------------------------


class _LandlockRulesetAttr(ctypes.Structure):
    """Maps to kernel ``struct landlock_ruleset_attr``. Packed to match the 8-byte kernel layout."""

    _pack_ = 1
    _fields_: ClassVar[list[tuple[str, type]]] = [("handled_access_fs", ctypes.c_uint64)]


class _LandlockPathBeneathAttr(ctypes.Structure):
    """Maps to kernel ``struct landlock_path_beneath_attr``. Packed to match the 12-byte kernel layout."""

    _pack_ = 1
    _fields_: ClassVar[list[tuple[str, type]]] = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_cached_libc: ctypes.CDLL | None = None


def _get_libc() -> ctypes.CDLL | None:
    """Load and cache libc for Landlock syscalls. Returns None if unavailable."""
    global _cached_libc  # noqa: PLW0603
    if _cached_libc is not None:
        return _cached_libc
    libc_name = ctypes.util.find_library("c")
    if not libc_name:
        return None
    try:
        libc = ctypes.CDLL(libc_name, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        _cached_libc = libc
        return libc
    except OSError:
        return None


def _set_no_new_privs() -> None:
    """Set PR_SET_NO_NEW_PRIVS so the subprocess cannot escalate privileges.

    Best-effort: failure is silently ignored. Landlock's ``restrict_self``
    requires this flag or ``CAP_SYS_ADMIN``.
    """
    libc = _get_libc()
    if not libc:
        return
    with contextlib.suppress(OSError, AttributeError):
        libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)


def _drop_supplementary_groups() -> None:
    """Drop all supplementary groups to reduce filesystem access scope.

    Best-effort: failure is silently ignored (e.g. unprivileged process).
    """
    with contextlib.suppress(OSError, PermissionError):
        os.setgroups([])


def _shell_quote(s: str) -> str:
    """Single-quote a string for safe embedding in a shell command."""
    return "'" + s.replace("'", "'\\''") + "'"


def _get_python_runtime_paths() -> list[str]:
    """Discover Python interpreter and stdlib paths at runtime.

    Returns resolved absolute paths for the interpreter directory and
    standard library. Paths under the venv (e.g. /opt/app-root/.venv)
    are excluded — only system paths under /usr are included. Scripts
    are stdlib-only by design.
    """
    paths = []
    real_exe = os.path.realpath(sys.executable)
    exe_dir = str(Path(real_exe).parent)
    if exe_dir and exe_dir.startswith("/usr"):
        paths.append(exe_dir)

    for key in ("stdlib", "platstdlib"):
        p = sysconfig.get_path(key)
        if p:
            real_p = os.path.realpath(p)
            if real_p not in paths and real_p.startswith("/usr"):
                paths.append(real_p)

    return paths


# ---------------------------------------------------------------------------
# Tier 1: Landlock LSM
# ---------------------------------------------------------------------------

_cached_landlock_abi: int | None = None


def _detect_landlock_abi() -> int:
    """Probe the kernel for Landlock support.

    Returns the ABI version (>= 1) on success, -1 on failure.
    Result is cached for the process lifetime.
    """
    global _cached_landlock_abi  # noqa: PLW0603
    if _cached_landlock_abi is not None:
        return _cached_landlock_abi

    libc = _get_libc()
    if not libc:
        _cached_landlock_abi = -1
        return -1

    try:
        result = libc.syscall(_NR_LANDLOCK_CREATE_RULESET, 0, 0, LANDLOCK_CREATE_RULESET_VERSION)
        _cached_landlock_abi = result if result >= 1 else -1
    except OSError:
        _cached_landlock_abi = -1

    return _cached_landlock_abi


def _handled_access_for_abi(abi: int) -> int:
    """Compute the handled_access_fs bitmask for a given ABI version."""
    if abi >= _LANDLOCK_ABI_V3:
        return _ABI_V3_MASK
    if abi >= _LANDLOCK_ABI_V2:
        return _ABI_V2_MASK
    return _ABI_V1_MASK


def _create_ruleset(handled_access_fs: int) -> int:
    """Create a Landlock ruleset. Returns the ruleset FD or -1."""
    libc = _get_libc()
    if not libc:
        return -1
    attr = _LandlockRulesetAttr(handled_access_fs=handled_access_fs)
    return int(
        libc.syscall(
            _NR_LANDLOCK_CREATE_RULESET,
            ctypes.byref(attr),
            ctypes.sizeof(attr),
            0,
        )
    )


def _add_path_rule(ruleset_fd: int, path: str, allowed_access: int) -> bool:
    """Add a path-beneath rule to a Landlock ruleset.

    Skips paths that don't exist on this system (returns True).
    For non-directory paths (files, device nodes, symlinks), READ_DIR
    is automatically stripped because the kernel rejects it with EINVAL.

    Args:
        ruleset_fd: File descriptor of the Landlock ruleset.
        path: Filesystem path to add (resolved via ``os.path.realpath``).
        allowed_access: Bitmask of ``LANDLOCK_ACCESS_FS_*`` rights to grant.

    Returns:
        True if the rule was added (or the path doesn't exist), False on
        syscall failure. Callers should treat False on critical paths
        (sandbox_dir, /usr) as a fatal sandbox setup error.

    """
    real_path = os.path.realpath(path)
    if not Path(real_path).exists():
        return True

    libc = _get_libc()
    if not libc:
        return False

    try:
        path_fd = os.open(real_path, O_PATH | O_CLOEXEC)
    except OSError:
        return False

    try:
        if not Path(real_path).is_dir():
            allowed_access = allowed_access & ~LANDLOCK_ACCESS_FS_READ_DIR

        attr = _LandlockPathBeneathAttr(
            allowed_access=allowed_access,
            parent_fd=path_fd,
        )
        result = libc.syscall(
            _NR_LANDLOCK_ADD_RULE,
            ruleset_fd,
            LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(attr),
            0,
        )
        return int(result) == 0
    finally:
        os.close(path_fd)


def _restrict_self(ruleset_fd: int) -> bool:
    """Apply the ruleset to the current process. Returns True on success."""
    libc = _get_libc()
    if not libc:
        return False
    result = libc.syscall(_NR_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0)
    return int(result) == 0


def _apply_landlock_sandbox(
    sandbox_dir: str,
    abi_version: int,
    extra_allowed_paths: list[str] | None = None,
) -> bool:
    """Apply Landlock filesystem restrictions to the current process.

    Non-critical rule failures (optional /etc files, /dev nodes) are
    tolerated — scripts may lose access to that path but the sandbox
    still holds. The sandbox_dir rule is critical — failure causes the
    entire apply to return False, which triggers ``os._exit(1)`` in
    the caller.

    Args:
        sandbox_dir: Ephemeral working directory the script writes to.
        abi_version: Landlock ABI version from ``_detect_landlock_abi``.
        extra_allowed_paths: Operator-configured additional read-only paths.

    Returns:
        True if Landlock was successfully applied, False on failure.

    """
    handled = _handled_access_for_abi(abi_version)
    ruleset_fd = _create_ruleset(handled)
    if ruleset_fd < 0:
        return False

    try:
        for path, access in ALLOWED_PATHS:
            _add_path_rule(ruleset_fd, path, access & handled)

        for py_path in _get_python_runtime_paths():
            _add_path_rule(ruleset_fd, py_path, _READ_EXECUTE & handled)

        # sandbox_dir is critical — scripts must be able to write here
        if not _add_path_rule(ruleset_fd, sandbox_dir, handled):
            return False

        if extra_allowed_paths:
            for p in extra_allowed_paths:
                _add_path_rule(ruleset_fd, p, _READ_ONLY & handled)

        return _restrict_self(ruleset_fd)
    finally:
        os.close(ruleset_fd)


# ---------------------------------------------------------------------------
# Tier 2: User namespace + mount namespace
# ---------------------------------------------------------------------------

_cached_unshare_userns: bool | None = None


def _detect_unshare_userns() -> bool:
    """Probe whether the full production unshare command works.

    Tests ``unshare --user --map-root-user --mount --pid --fork
    --kill-child`` with ``mount --make-rprivate /``.
    Result is cached for the process lifetime.
    """
    global _cached_unshare_userns  # noqa: PLW0603
    if _cached_unshare_userns is not None:
        return _cached_unshare_userns

    if shutil.which("unshare") is None:
        _cached_unshare_userns = False
        return False

    try:
        result = _sp.run(
            [  # noqa: S607
                "unshare",
                "--user",
                "--map-root-user",
                "--mount",
                "--pid",
                "--fork",
                "--kill-child",
                "bash",
                "-c",
                "mount --make-rprivate /",
            ],
            check=False,
            capture_output=True,
            timeout=5,
        )
        _cached_unshare_userns = result.returncode == 0
    except Exception:  # noqa: BLE001
        _cached_unshare_userns = False

    return _cached_unshare_userns


def _build_bind_mounts(parts: list[str]) -> None:
    """Bind-mount allowed directories into the new root."""
    for bind_dir in _TIER2_BIND_DIRS:
        real = os.path.realpath(bind_dir)
        if Path(real).is_dir():
            qr = _shell_quote(real)
            parts.append(f"mkdir -p $NEWROOT{qr}")
            parts.append(f"mount --bind {qr} $NEWROOT{qr}")


def _build_dev_mounts(parts: list[str]) -> None:
    """Bind-mount individual device nodes (not all of /dev, avoids /dev/shm)."""
    parts.append("mkdir -p $NEWROOT/dev")
    for dev_node in _TIER2_DEV_NODES:
        if Path(dev_node).exists():
            qd = _shell_quote(dev_node)
            parts.append(f"touch $NEWROOT{qd}")
            parts.append(f"mount --bind {qd} $NEWROOT{qd}")


def _build_etc_mounts(parts: list[str]) -> None:
    """Bind-mount individual /etc files and directories."""
    parts.append("mkdir -p $NEWROOT/etc")
    for etc_path in _TIER2_ETC_FILES:
        real = os.path.realpath(etc_path)
        if not Path(real).exists():
            continue
        rel = os.path.relpath(real, "/")
        qr = _shell_quote(real)
        qrel = _shell_quote(rel)
        if Path(real).is_dir():
            parts.append(f"mkdir -p $NEWROOT/{qrel}")
            parts.append(f"mount --bind {qr} $NEWROOT/{qrel}")
        else:
            parent = _shell_quote(str(Path(rel).parent))
            parts.append(f"mkdir -p $NEWROOT/{parent}")
            parts.append(f"touch $NEWROOT/{qrel}")
            parts.append(f"mount --bind {qr} $NEWROOT/{qrel}")


def _build_symlinks(parts: list[str]) -> None:
    """Create RHEL compat symlinks (/bin -> /usr/bin etc.)."""
    for link, target in [("/bin", "/usr/bin"), ("/sbin", "/usr/sbin"), ("/lib", "/usr/lib"), ("/lib64", "/usr/lib64")]:
        real_link = os.path.realpath(link)
        real_target = os.path.realpath(target)
        if real_link == real_target and Path(link).is_symlink():
            parts.append(f"ln -sf {target} $NEWROOT{link}")


def _build_extra_paths(parts: list[str], extra_allowed_paths: list[str] | None) -> None:
    """Bind-mount extra operator-configured paths (directories and files)."""
    if not extra_allowed_paths:
        return
    for p in extra_allowed_paths:
        real = os.path.realpath(p)
        qr = _shell_quote(real)
        if Path(real).is_dir():
            parts.append(f"mkdir -p $NEWROOT{qr}")
            parts.append(f"mount --bind {qr} $NEWROOT{qr}")
        elif Path(real).exists():
            parent = _shell_quote(str(Path(real).parent))
            parts.append(f"mkdir -p $NEWROOT/{parent}")
            parts.append(f"touch $NEWROOT{qr}")
            parts.append(f"mount --bind {qr} $NEWROOT{qr}")


def _build_python_runtime_mounts(parts: list[str]) -> None:
    """Bind-mount Python runtime paths."""
    for py_path in _get_python_runtime_paths():
        if Path(py_path).is_dir():
            qp = _shell_quote(py_path)
            parts.append(f"mkdir -p $NEWROOT{qp}")
            parts.append(f"mount --bind {qp} $NEWROOT{qp}")


def _build_pivot_and_exec(
    parts: list[str],
    sandbox_dir: str,
    command: list[str],
) -> None:
    """Pivot root, detach old root, drop privileges, and exec the script."""
    # /tmp inside the new root for scripts that ignore TMPDIR
    parts.append("mkdir -p $NEWROOT/tmp")
    parts.append("chmod 1777 $NEWROOT/tmp")

    # Pivot root and detach old root.
    # After pivot_root, /old contains the original filesystem (including
    # secrets). Try umount -l first (needs /proc); fall back to a tmpfs
    # overlay if umount fails.
    parts.append("mkdir -p $NEWROOT/old")
    parts.append("pivot_root $NEWROOT $NEWROOT/old")
    parts.append(f"cd {_shell_quote(sandbox_dir)}")
    parts.append(
        "if umount -l /old 2>/dev/null; then "
        "rmdir /old 2>/dev/null || true; "
        "else mount -t tmpfs tmpfs /old || exit 1; fi"
    )

    # Make sandbox dir and /tmp world-writable before dropping privileges,
    # so the unprivileged nested user namespace can write to them.
    parts.append(f"chmod 1777 {_shell_quote(sandbox_dir)}")
    parts.append("chmod 1777 /tmp 2>/dev/null || true")

    # Execute the script inside a nested user namespace (without
    # --map-root-user) so it runs as an unprivileged user and cannot
    # umount the /old overlay or perform other mount operations.
    if command[0] == "bash":
        script_exec = f"bash -c {_shell_quote(command[2])}"
    else:
        script_exec = f"{_shell_quote(command[0])} -c {_shell_quote(command[2])}"
    parts.append(f"exec unshare --user -- {script_exec}")


def build_pivot_root_command(
    command: list[str],
    sandbox_dir: str,
    extra_allowed_paths: list[str] | None = None,
) -> list[str]:
    """Wrap *command* in a fully isolated unshare sandbox.

    The wrapper does (in order):
    1. ``unshare --user --map-root-user --mount --pid --fork --kill-child``
    2. Bind-mount only allowlisted paths into a tmpfs new root
    3. ``pivot_root`` into the new root
    4. Detach the old root (``umount -l``; tmpfs overlay as fallback)
    5. ``chmod 1777`` the sandbox dir so the nested userns can write
    6. ``exec unshare --user --`` to drop ``CAP_SYS_ADMIN`` before
       running the script (prevents ``umount /old``)

    ``--pid --fork`` creates a PID namespace so /proc only shows the
    script. ``--kill-child`` reaps the forked PID 1 on activity timeout.

    Args:
        command: Must be ``[interpreter, "-c", source_code]``.
        sandbox_dir: Ephemeral working directory for the script.
        extra_allowed_paths: Operator-configured additional paths to
            bind-mount (read-only for directories, read for files).

    Returns:
        The wrapped command list for ``asyncio.create_subprocess_exec``.

    """
    parts = [
        "set -e",
        "mount --make-rprivate /",
        "NEWROOT=$(mktemp -d)",
        "mount -t tmpfs tmpfs $NEWROOT",
    ]

    _build_bind_mounts(parts)
    _build_dev_mounts(parts)
    _build_etc_mounts(parts)

    # Fresh procfs (may fail in restricted container runtimes)
    parts.append("mkdir -p $NEWROOT/proc")
    parts.append("mount -t proc proc $NEWROOT/proc 2>/dev/null || true")

    # Sandbox working directory
    parts.append(f"mkdir -p $NEWROOT{_shell_quote(sandbox_dir)}")

    _build_symlinks(parts)
    _build_extra_paths(parts, extra_allowed_paths)
    _build_python_runtime_mounts(parts)
    _build_pivot_and_exec(parts, sandbox_dir, command)

    wrapper = "; ".join(parts)
    return ["unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork", "--kill-child", "bash", "-c", wrapper]


# ---------------------------------------------------------------------------
# Preexec and context
# ---------------------------------------------------------------------------


SANDBOX_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def sanitize_env_for_sandbox(env: dict[str, str], sandbox_dir: str) -> dict[str, str]:
    """Replace PATH and temp directory vars for sandboxed execution.

    PATH is restricted to standard system directories (the worker's PATH
    may include directories outside the allowlist). TMPDIR, TMP, and TEMP
    are set to the sandbox directory so Python's tempfile, bash mktemp,
    and other tools write there instead of host /tmp (which is blocked
    under Landlock). HOME is left as the worker home (writes to ~ will
    fail under the allowlist).

    Args:
        env: Original environment dict (not mutated).
        sandbox_dir: Ephemeral sandbox directory path.

    Returns:
        A new dict with sanitized PATH and temp vars.

    """
    env = dict(env)
    env["PATH"] = SANDBOX_PATH
    env["TMPDIR"] = sandbox_dir
    env["TMP"] = sandbox_dir
    env["TEMP"] = sandbox_dir
    return env


def resolve_python_executable() -> str:
    """Return the real path to the Python interpreter.

    Under Landlock, venv symlinks (e.g. /opt/app-root/.venv/bin/python3)
    point to paths outside the allowlist. The real path
    (e.g. /usr/bin/python3.12) is on the allowlist.

    Returns:
        Absolute resolved path to the Python binary.

    """
    return os.path.realpath(sys.executable)


def sandbox_preexec_fn(
    sandbox_dir: str,
    *,
    apply_landlock: bool = False,
    abi_version: int = -1,
    extra_allowed_paths: list[str] | None = None,
) -> None:
    """Pre-exec function applied to every script subprocess.

    Called after fork() but before exec() — changes are confined to the
    child process and do not affect the Temporal worker. Always applies
    baseline hardening (CWD, umask, no_new_privs, groups). When
    ``apply_landlock`` is True, also applies Landlock; if Landlock
    application fails, calls ``os._exit(1)`` with a stderr message
    so the script never executes without isolation.

    Args:
        sandbox_dir: Ephemeral working directory for the script.
        apply_landlock: Whether to apply Landlock filesystem restrictions.
        abi_version: Landlock ABI version (from ``_detect_landlock_abi``).
        extra_allowed_paths: Additional read-only paths for the allowlist.

    THREADING CAVEAT: Temporal workers are multi-threaded. When fork() is
    called, only the calling thread is copied; locks held by other threads
    remain locked in the child. This function uses only thin POSIX wrappers
    (os.chdir, os.umask, os.open, os.close) and direct ctypes syscalls to
    minimize deadlock risk. If deadlocks are observed in production,
    replace the Landlock application with a compiled helper binary invoked
    before exec.

    """
    with contextlib.suppress(OSError):
        os.chdir(sandbox_dir)
    os.umask(0o077)
    _set_no_new_privs()
    _drop_supplementary_groups()

    if (
        apply_landlock
        and abi_version >= 1
        and not _apply_landlock_sandbox(sandbox_dir, abi_version, extra_allowed_paths)
    ):
        sys.stderr.write("FATAL: Landlock sandbox failed to apply — refusing to exec\n")
        sys.stderr.flush()
        os._exit(1)


# Prefixes that operators must not add via extra_allowed_paths — they would
# undermine the sandbox by exposing secrets or the entire filesystem.
# Checked by prefix so /etc/secrets and /run/secrets are also rejected.
_DENIED_EXTRA_PREFIXES: tuple[str, ...] = (
    "/proc",
    "/etc",
    "/run",
    "/dev",
    "/sys",
    "/tmp",  # noqa: S108
    "/home",
    "/root",
    "/opt",
    "/var",
)


def _validate_extra_allowed_paths(paths: list[str] | None) -> None:
    """Reject extra_allowed_paths that would undermine the sandbox.

    Denied prefixes: ``/proc``, ``/etc``, ``/run``, ``/dev``, ``/sys``,
    ``/tmp``, ``/home``, ``/root``, ``/opt``, ``/var``, and ``/``.
    """
    if not paths:
        return
    for p in paths:
        # Check both the raw path and the resolved path (macOS resolves
        # /tmp → /private/tmp, /var → /private/var, /etc → /private/etc)
        candidates = {p, os.path.realpath(p)}
        for candidate in candidates:
            if candidate == "/":
                msg = "extra_allowed_paths cannot include '/' — it would undermine the sandbox"
                raise ValueError(msg)
        for candidate in candidates:
            for prefix in _DENIED_EXTRA_PREFIXES:
                if candidate == prefix or candidate.startswith(prefix + "/"):
                    msg = f"extra_allowed_paths cannot include {p!r} — it would undermine the sandbox"
                    raise ValueError(msg)


def create_sandbox_context(
    *,
    sandbox_enabled: bool,
    extra_allowed_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Prepare sandbox artefacts for a single script execution.

    Args:
        sandbox_enabled: Whether to require filesystem isolation.
        extra_allowed_paths: Operator-configured additional paths.

    Returns:
        A dict with:
        - ``sandbox_dir``: path to the ephemeral temp directory.
        - ``tier``: active tier (``landlock``, ``unshare``, or ``baseline``).
          ``baseline`` is only returned when ``sandbox_enabled`` is False.
        - ``preexec_fn``: callable for ``subprocess.Popen(preexec_fn=…)``.
        - ``extra_allowed_paths``: (unshare tier only) passed through for
          ``build_pivot_root_command``.

    Raises:
        RuntimeError: If ``sandbox_enabled`` is True but neither Landlock nor
            unshare is available (fail-closed).
        ValueError: If ``extra_allowed_paths`` contains a denied prefix.

    """
    _validate_extra_allowed_paths(extra_allowed_paths)
    sandbox_dir = tempfile.mkdtemp(prefix="script-sandbox-")

    if not sandbox_enabled:

        def _preexec() -> None:
            sandbox_preexec_fn(sandbox_dir)

        return {
            "sandbox_dir": sandbox_dir,
            "tier": "baseline",
            "preexec_fn": _preexec,
        }

    abi = _detect_landlock_abi()
    if abi >= 1:

        def _preexec() -> None:
            sandbox_preexec_fn(
                sandbox_dir,
                apply_landlock=True,
                abi_version=abi,
                extra_allowed_paths=extra_allowed_paths,
            )

        return {
            "sandbox_dir": sandbox_dir,
            "tier": "landlock",
            "preexec_fn": _preexec,
        }

    if _detect_unshare_userns():

        def _preexec() -> None:
            sandbox_preexec_fn(sandbox_dir)

        return {
            "sandbox_dir": sandbox_dir,
            "tier": "unshare",
            "extra_allowed_paths": extra_allowed_paths,
            "preexec_fn": _preexec,
        }

    cleanup_sandbox(sandbox_dir)
    msg = (
        "Script sandbox is enabled but neither Landlock LSM nor "
        "unshare --user --mount is available. Script execution refused. "
        "Install util-linux, enable user namespaces, or upgrade "
        "to a kernel with Landlock support."
    )
    raise RuntimeError(msg)


def cleanup_sandbox(sandbox_dir: str) -> None:
    """Remove the ephemeral sandbox directory. Errors are silently ignored."""
    with contextlib.suppress(Exception):
        shutil.rmtree(sandbox_dir, ignore_errors=True)
