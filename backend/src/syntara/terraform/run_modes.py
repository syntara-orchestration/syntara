"""Map SDP Trigger Run modes to TFE POST /runs attributes."""

from __future__ import annotations

from typing import Any

from syntara.terraform.errors import TFEError, TFEErrorCode

RUN_MODES = frozenset(
    {
        "plan-and-apply",
        "plan-only",
        "destroy",
        "refresh-only",
        "targeted-resource",
        "replace-resource",
        "allow-empty-apply",
    }
)

_BASE_MODE_ATTRS: dict[str, dict[str, Any]] = {
    "plan-and-apply": {"plan-only": False, "auto-apply": True},
    "plan-only": {"plan-only": True},
    "destroy": {"is-destroy": True},
    "refresh-only": {"refresh-only": True},
    "allow-empty-apply": {"plan-only": False, "auto-apply": True, "allow-empty-apply": True},
}


def map_run_mode(
    mode: str,
    *,
    target_resources: list[str] | None = None,
    replace_resources: list[str] | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Build POST /runs attributes for a supported mode.

    Raises:
        TFEError: VALIDATION if mode is unknown or required addresses are missing.

    """
    if mode not in RUN_MODES:
        supported = ", ".join(sorted(RUN_MODES))
        msg = f"Unsupported run mode '{mode}'. Supported: {supported}"
        raise TFEError(msg, error_code=TFEErrorCode.VALIDATION)

    attrs: dict[str, Any] = {}
    if message:
        attrs["message"] = message

    if mode in _BASE_MODE_ATTRS:
        attrs.update(_BASE_MODE_ATTRS[mode])
        return attrs

    if mode == "targeted-resource":
        if not target_resources:
            msg = "targeted-resource mode requires targetResources"
            raise TFEError(msg, error_code=TFEErrorCode.VALIDATION)
        attrs.update({"plan-only": False, "auto-apply": True, "target-addrs": target_resources})
        return attrs

    # replace-resource
    if not replace_resources:
        msg = "replace-resource mode requires replaceResources"
        raise TFEError(msg, error_code=TFEErrorCode.VALIDATION)
    attrs.update({"plan-only": False, "auto-apply": True, "replace-addrs": replace_resources})
    return attrs
