"""Top-level Syntara package exposing subpackages for agents, API, and tool manager."""

# regopy (rego-cpp) must be imported before any module that loads greenlet or
# temporalio's native bridge: librego_shared.so statically links snmalloc and
# exports operator new/delete; if another native library loads first, libstdc++
# allocation symbols bind across two allocators and every rego query leaks
# ~69 KB natively (backend OOM, AAP-XXXXX). Loading regopy first makes the
# bindings consistent. Guarded because E2E CI images without libatomic.so.1
# cannot import regopy at all (PR #560); those processes never evaluate rego.
# See docs/standards/imports-and-modules.md ("Native import order").
_REGOPY_PRELOAD_ERROR: str | None = None
try:
    import regopy  # type: ignore[import-untyped]
except (ImportError, OSError) as _exc:
    # Only the known environment gaps are tolerated (PR #560: UBI9 E2E images
    # without libatomic.so.1, or regopy not installed at all). Anything else
    # is an unexpected loader failure and must surface immediately.
    if isinstance(_exc, ModuleNotFoundError) or "cannot open shared object file" in str(_exc):
        _REGOPY_PRELOAD_ERROR = str(_exc)
    else:
        raise

__all__ = ["api", "tool_manager"]
