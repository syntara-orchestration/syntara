"""Top-level Syntara package exposing subpackages for agents, API, and tool manager."""

# regopy (rego-cpp) must be imported before any module that loads greenlet or
# temporalio's native bridge: librego_shared.so statically links snmalloc and
# exports operator new/delete; if another native library loads first, libstdc++
# allocation symbols bind across two allocators and every rego query leaks
# ~69 KB natively. Loading regopy first makes the
# bindings consistent. Guarded because E2E CI images without libatomic.so.1
# cannot import regopy at all (PR #560); those processes never evaluate rego.
# See docs/standards/imports-and-modules.md ("Native import order").
_REGOPY_PRELOAD_ERROR: str | None = None
try:
    import regopy  # type: ignore[import-untyped]
except (ImportError, OSError) as _exc:
    # Only the two known environment gaps are tolerated: regopy itself not
    # installed (collection-only envs), and the UBI9 E2E images that lack
    # libatomic.so.1 (PR #560). A missing transitive dependency or any other
    # unloadable shared object is a packaging fault and must surface
    # immediately, not run without the preload.
    _regopy_not_installed = isinstance(_exc, ModuleNotFoundError) and _exc.name == "regopy"
    _libatomic_gap = "libatomic.so.1: cannot open shared object file" in str(_exc)
    if _regopy_not_installed or _libatomic_gap:
        _REGOPY_PRELOAD_ERROR = str(_exc)
    else:
        raise

__all__ = ["api", "tool_manager"]
