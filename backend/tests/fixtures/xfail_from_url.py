"""Dynamically xfail tests listed at a remote URL.

When ``--xfail-from-url`` is passed, fetches a Markdown file and parses
``# `` headings as test node-id patterns.  The text below each heading is
used as the xfail reason.  Each entry can be a directory, file, or full
test node-id — matching tests are marked *xfail*.

If the fetch fails (network, auth, …) the run continues without marking
anything (fail-open).
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
import structlog

logger = structlog.stdlib.get_logger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("url_xfail", "dynamic xfail from URL")
    group.addoption(
        "--xfail-from-url",
        default=None,
        help="URL or file path of a Markdown file listing tests to mark as xfail",
    )


def _is_file_path(source: str) -> bool:
    return source.startswith(("/", "./", "../"))


def _load_xfail_file(source: str) -> str | None:
    """Load the xfail Markdown file from a URL or local path."""
    if _is_file_path(source):
        path = Path(source)
        try:
            return path.read_text()
        except OSError as exc:
            logger.warning("url_xfail: failed to read file", path=str(path), error=str(exc))
            return None

    try:
        response = httpx.get(source, timeout=30, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("url_xfail: failed to fetch file", url=source, error=str(exc))
        return None

    return response.text


_HEADING_RE = re.compile(r"^#\s+(.+)$")


def _parse_xfail_entries(content: str) -> list[tuple[str, str]]:
    """Parse H1 headings as test node-ids with the following text as the reason."""
    entries: list[tuple[str, str]] = []
    current_pattern: str | None = None
    reason_lines: list[str] = []

    def _flush() -> None:
        if current_pattern is not None:
            reason = " ".join(reason_lines).strip() or "listed in xfail list"
            entries.append((current_pattern, reason))

    for line in content.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            _flush()
            current_pattern = match.group(1).strip()
            reason_lines = []
        elif current_pattern is not None:
            stripped = line.strip()
            if stripped:
                reason_lines.append(stripped)

    _flush()
    return entries


def _matches(nodeid: str, pattern: str) -> bool:
    """Check whether *nodeid* matches *pattern*.

    A pattern is treated as a prefix when it looks like a directory or file
    path (no ``::``), and as an exact match otherwise.
    """
    if "::" in pattern:
        return nodeid == pattern
    return nodeid.startswith(pattern)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    source: str | None = config.getoption("--xfail-from-url")
    if not source:
        return
    content = _load_xfail_file(source)
    if content is None:
        return

    entries = _parse_xfail_entries(content)
    if not entries:
        logger.info("url_xfail: no patterns found in file")
        return

    patterns = [e[0] for e in entries]
    logger.info("url_xfail: loaded patterns", count=len(entries), patterns=patterns)

    matched = 0
    for item in items:
        for pattern, reason in entries:
            if _matches(item.nodeid, pattern):
                item.add_marker(pytest.mark.xfail(reason=f"url xfail: {reason}"))
                matched += 1
                break

    logger.info("url_xfail: marked tests", matched=matched, total=len(items))
