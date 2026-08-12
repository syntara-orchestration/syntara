"""Unit tests for syntara.files.utils."""

from pathlib import Path
from unittest.mock import patch

import pytest

from syntara.files.utils import cleanup_files


@pytest.fixture
def tmp_files(tmp_path: Path) -> list[str]:
    """Create temporary files and return their paths as strings."""
    paths = []
    for name in ("a.txt", "b.txt"):
        f = tmp_path / name
        f.write_text("data")
        paths.append(str(f))
    return paths


class TestCleanupFiles:
    """Tests for cleanup_files."""

    async def test_empty_list(self) -> None:
        await cleanup_files([])

    async def test_deletes_existing_files(self, tmp_files: list[str], tmp_path: Path) -> None:
        await cleanup_files(tmp_files)

        for file_path in tmp_files:
            assert not Path(file_path).exists()

    async def test_skips_nonexistent_files(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "no_such_file.txt")
        await cleanup_files([missing])

    async def test_context_logged_when_provided(self, tmp_files: list[str]) -> None:
        with patch("syntara.files.utils.logger") as mock_logger:
            await cleanup_files(tmp_files, context="after validation failure")

            for call in mock_logger.info.call_args_list:
                assert "after validation failure" in call.kwargs["context"]

    async def test_continues_on_deletion_error(self, tmp_files: list[str]) -> None:
        original_unlink = Path.unlink

        def failing_unlink(self: Path, *args: object, **kwargs: object) -> None:
            if self.name == "a.txt":
                msg = "denied"
                raise PermissionError(msg)
            original_unlink(self)

        with patch.object(Path, "unlink", failing_unlink):
            await cleanup_files(tmp_files)

        assert Path(tmp_files[0]).exists()
        assert not Path(tmp_files[1]).exists()
