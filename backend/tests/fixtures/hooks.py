"""Pytest hooks: logging setup, performance marker, worker_id fixture, and cleanup."""

import tempfile
from pathlib import Path

import pytest
import structlog

from syntara.core.logging.logging import configure_app_logging

configure_app_logging()

logger = structlog.stdlib.get_logger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for pytest."""
    parser.addoption(
        "--run-performance",
        action="store_true",
        default=False,
        help="Run performance tests (excluded by default)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip performance tests unless --run-performance is provided."""
    if not config.getoption("--run-performance"):
        skip_performance = pytest.mark.skip(reason="need --run-performance option to run")
        for item in items:
            if "performance" in item.keywords:
                item.add_marker(skip_performance)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Clean up lock files after test session completes."""
    temp_dir = Path(tempfile.gettempdir())
    lock_pattern = "nexus_router_discovery_gw*.lock"

    for lock_file in temp_dir.glob(lock_pattern):
        try:
            lock_file.unlink()
            logger.debug("Cleaned up test lock file: %s", lock_file)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("Failed to clean up lock file %s: %s", lock_file, e)


@pytest.fixture(scope="session")
def worker_id(request: pytest.FixtureRequest) -> str:
    """Get pytest-xdist worker ID."""
    if hasattr(request.config, "workerinput"):
        return request.config.workerinput["workerid"]  # type: ignore[no-any-return]
    return "master"
