#!/usr/bin/env python3.12
"""Strip optional/integration metadata from pyproject.toml for hermetic builds."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

SECTIONS_TO_REMOVE = {
    "[project.optional-dependencies]",
    "[dependency-groups]",
}
LINUX_ONLY_ENV = "environments = [\"sys_platform == 'linux'\"]\n"


@dataclass
class _SanitizeState:
    in_uv_sources: bool = False
    in_tool_uv: bool = False
    saw_tool_uv: bool = False
    tool_uv_has_env: bool = False


def _skip_section(lines: list[str], index: int) -> int:
    """Skip all non-header lines within a TOML section."""
    index += 1
    while index < len(lines) and not lines[index].startswith("["):
        index += 1
    return index


def _is_table_header(stripped: str) -> bool:
    return stripped.startswith("[") and stripped.endswith("]")


def _handle_table_header(stripped: str, out: list[str], state: _SanitizeState) -> None:
    if state.in_tool_uv and not state.tool_uv_has_env:
        out.append(LINUX_ONLY_ENV)

    if stripped == "[tool.uv.sources]" and not state.saw_tool_uv:
        out.extend(["[tool.uv]\n", LINUX_ONLY_ENV, "\n"])
        state.saw_tool_uv = True

    state.in_uv_sources = stripped == "[tool.uv.sources]"
    state.in_tool_uv = stripped == "[tool.uv]"
    if state.in_tool_uv:
        state.saw_tool_uv = True
        state.tool_uv_has_env = False


def _replace_tool_uv_environment(stripped: str, out: list[str], state: _SanitizeState) -> bool:
    if not (state.in_tool_uv and stripped.startswith("environments =")):
        return False

    if not state.tool_uv_has_env:
        out.append(LINUX_ONLY_ENV)
        state.tool_uv_has_env = True
    return True


def _finalize_output(out: list[str], state: _SanitizeState) -> None:
    if state.in_tool_uv and not state.tool_uv_has_env:
        out.append(LINUX_ONLY_ENV)

    if not state.saw_tool_uv:
        if out and out[-1].strip():
            out.append("\n")
        out.extend(["[tool.uv]\n", LINUX_ONLY_ENV])


def sanitize_pyproject(pyproject_path: Path) -> None:
    """Remove non-hermetic metadata and enforce Linux-only uv environments."""
    lines = pyproject_path.read_text().splitlines(keepends=True)
    out: list[str] = []
    i = 0
    state = _SanitizeState()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped in SECTIONS_TO_REMOVE:
            i = _skip_section(lines, i)
            continue

        if _is_table_header(stripped):
            _handle_table_header(stripped, out, state)

        if state.in_uv_sources and stripped.startswith("external-services"):
            i += 1
            continue

        # Konflux prefetches this VCS dependency from requirements.txt as a
        # local source archive. Drop the Git source override so the offline
        # lock resolves that prefetched execution-plane==version artifact.
        if state.in_uv_sources and stripped.startswith("execution-plane ="):
            i += 1
            continue

        if _replace_tool_uv_environment(stripped, out, state):
            i += 1
            continue

        out.append(line)
        i += 1

    _finalize_output(out, state)

    new_text = "".join(out)
    tomllib.loads(new_text)  # fail fast if sanitization produced invalid TOML
    pyproject_path.write_text(new_text)


def main() -> int:
    """Sanitize a pyproject.toml file in place for hermetic builds."""
    path_arg = sys.argv[1] if len(sys.argv) > 1 else "pyproject.toml"
    sanitize_pyproject(Path(path_arg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
