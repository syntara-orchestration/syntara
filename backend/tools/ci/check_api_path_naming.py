"""Check that API endpoint paths use snake_case (no hyphens).

Scans all Python files under src/syntara/ for FastAPI router definitions and
verifies that URL path segments do not contain hyphens. Path parameters
(e.g., {project_id}) are ignored.

Usage:
    uv run python tools/ci/check_api_path_naming.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src" / "syntara"

RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"

PREFIX_RE = re.compile(r"""(?:APIRouter|NexusRouter)\(\s*prefix\s*=\s*["']([^"']+)["']""")
ROUTE_RE = re.compile(r"""@\w+\.(?:get|post|put|patch|delete|head|options)\(\s*["']([^"']+)["']""")


def _has_hyphen_segment(path: str) -> list[str]:
    """Return path segments that contain hyphens (excluding path params)."""
    return [seg for seg in path.strip("/").split("/") if "-" in seg and not seg.startswith("{")]


def check_file(filepath: Path) -> list[tuple[int, str, list[str]]]:
    """Check a single file for hyphenated path segments.

    Returns list of (line_number, path, bad_segments) tuples.
    """
    violations: list[tuple[int, str, list[str]]] = []
    try:
        lines = filepath.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return violations

    for i, line in enumerate(lines, 1):
        for pattern in (PREFIX_RE, ROUTE_RE):
            for match in pattern.finditer(line):
                path = match.group(1)
                bad = _has_hyphen_segment(path)
                if bad:
                    violations.append((i, path, bad))
    return violations


def main() -> int:
    """Scan router files and report any hyphenated API path segments."""
    all_violations: list[tuple[Path, int, str, list[str]]] = []

    for filepath in sorted(SRC_DIR.rglob("*.py")):
        if "__pycache__" in filepath.parts:
            continue
        for line_num, path, bad_segments in check_file(filepath):
            all_violations.append((filepath, line_num, path, bad_segments))

    if all_violations:
        print(f"\n{RED}Found {len(all_violations)} API path(s) with hyphens:{RESET}\n")
        for filepath, line_num, path, bad_segments in all_violations:
            rel = filepath.relative_to(ROOT)
            print(f"  {rel}:{line_num}: {path}")
            print(f"    hyphenated segments: {', '.join(bad_segments)}")
        print(f"\n{RED}API paths must use snake_case (underscores), not kebab-case (hyphens).{RESET}\n")
        return 1

    print(f"{GREEN}All API paths use snake_case.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
