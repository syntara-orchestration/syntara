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

    A pattern without ``::`` is treated as a directory/file prefix.

    A pattern with ``::`` mirrors pytest's own node-id selection: the base id
    of a test also selects its parametrizations and (for a class base id) its
    methods. So ``test_foo.py::test_bar`` matches ``test_foo.py::test_bar`` and
    ``test_foo.py::test_bar[case-1]``, and ``test_foo.py::TestC`` matches
    ``test_foo.py::TestC::test_m[a-b]``. Without this, a flaky parametrized
    test quarantined by its base id would not be marked xfail and would fail
    the suite.
    """
    if "::" in pattern:
        # ``pattern[`` = parametrized instance; ``pattern::`` = class/module
        # base id selecting its sub-items.
        return nodeid == pattern or nodeid.startswith((f"{pattern}[", f"{pattern}::"))
    return nodeid.startswith(pattern)


# Cache the parsed entries on the session config so the file is fetched once and
# shared between pytest_report_header and pytest_collection_modifyitems.
_ENTRIES_KEY: pytest.StashKey[list[tuple[str, str]]] = pytest.StashKey()


def _get_entries(config: pytest.Config) -> list[tuple[str, str]]:
    """Load and cache the parsed xfail entries for this session (fail-open to [])."""
    if _ENTRIES_KEY in config.stash:
        return config.stash[_ENTRIES_KEY]

    source: str | None = config.getoption("--xfail-from-url")
    entries: list[tuple[str, str]] = []
    if source:
        content = _load_xfail_file(source)
        if content is not None:
            entries = _parse_xfail_entries(content)
    config.stash[_ENTRIES_KEY] = entries
    return entries


def pytest_report_header(config: pytest.Config) -> list[str] | None:
    """Print the active xfail rules at the start of the run."""
    entries = _get_entries(config)
    if not entries:
        return None
    source = config.getoption("--xfail-from-url")
    lines = [f"url xfail: {len(entries)} rule(s) from {source}"]
    lines += [f"  {pattern} — {reason}" for pattern, reason in entries]
    return lines


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    entries = _get_entries(config)
    if not entries:
        return

    matched = 0
    for item in items:
        for pattern, reason in entries:
            if _matches(item.nodeid, pattern):
                item.add_marker(pytest.mark.xfail(reason=f"url xfail: {reason}"))
                matched += 1
                break

    logger.info("url_xfail: marked tests", matched=matched, total=len(items), patterns=[e[0] for e in entries])
