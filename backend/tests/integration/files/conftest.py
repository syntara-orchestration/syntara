"""Shared fixtures for file upload integration tests."""

from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from tests.fixtures.files import get_fixtures_dir


@pytest_asyncio.fixture(autouse=True)
async def _seed_data(_seed_integration_data: None) -> None:
    """Opt into shared authz + builtin workflow seeding."""


@pytest_asyncio.fixture
async def test_project_id(test_db_session: AsyncSession) -> str:
    """Create a test project and return its ID as a string."""
    project = Project(name=f"test-project-{uuid4().hex[:8]}", description="Test project for files")
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return str(project.id)


@pytest.fixture
def fixtures_dir() -> Path:
    """Provide fixtures directory path."""
    return get_fixtures_dir()


@pytest.fixture
def sample_pdf_path(fixtures_dir: Path) -> Path:
    """Provide path to sample PDF file."""
    return fixtures_dir / "sample.pdf"


@pytest.fixture
def sample_docx_path(fixtures_dir: Path) -> Path:
    """Provide path to sample DOCX file."""
    return fixtures_dir / "sample.docx"


@pytest.fixture
def sample_txt_path(fixtures_dir: Path) -> Path:
    """Provide path to sample text file."""
    return fixtures_dir / "sample.txt"


@pytest.fixture
def sample_md_path(fixtures_dir: Path) -> Path:
    """Provide path to sample markdown file."""
    return fixtures_dir / "sample.md"


@pytest.fixture
def sample_image_path(fixtures_dir: Path) -> Path:
    """Provide path to sample image file."""
    return fixtures_dir / "image.png"
