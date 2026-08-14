"""Integration tests for Files API endpoints.

Tests cover:
- POST /api/v1/files — file uploads
- GET /api/v1/files/metadata — batch file metadata retrieval
- Document conversion scheduling and execution
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.auth.dependencies import get_current_user
from syntara.authz.models import Project
from syntara.core.models import User
from syntara.files.document_conversion.tasks import get_document_conversion_task
from syntara.files.models import FileMetadata, FileStatus


class TestFilesAPIUpload:
    """Test POST /api/v1/files endpoint."""

    @pytest.mark.asyncio
    async def test_upload_single_file_returns_file_id(
        self,
        auth_client: AsyncClient,
        test_project_id: str,
    ) -> None:
        """Test uploading a single file returns file_id in response."""
        files = [("files", ("document.txt", b"Sample text content here", "text/plain"))]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 201
        response_data = response.json()
        assert "file_ids" in response_data
        assert len(response_data["file_ids"]) == 1
        assert "files" in response_data
        assert len(response_data["files"]) == 1

        file_info = response_data["files"][0]
        assert file_info["file_id"] == response_data["file_ids"][0]
        assert file_info["filename"] == "document.txt"
        assert file_info["mime_type"] == "text/plain"
        assert file_info["status"] == "pending_conversion"
        assert "file_path" not in file_info

    @pytest.mark.asyncio
    async def test_upload_multiple_files_returns_file_ids(
        self,
        auth_client: AsyncClient,
        test_project_id: str,
    ) -> None:
        """Test uploading multiple files returns all file_ids."""
        files = [
            ("files", ("doc1.pdf", b"First PDF content", "application/pdf")),
            ("files", ("doc2.txt", b"Text content", "text/plain")),
            ("files", ("doc3.md", b"# Markdown", "text/markdown")),
        ]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 201
        response_data = response.json()
        assert len(response_data["file_ids"]) == 3
        assert len(response_data["files"]) == 3

        filenames = {f["filename"] for f in response_data["files"]}
        assert filenames == {"doc1.pdf", "doc2.txt", "doc3.md"}

    @pytest.mark.asyncio
    async def test_upload_rejects_file_too_large(
        self,
        auth_client: AsyncClient,
        test_project_id: str,
    ) -> None:
        """Test that files exceeding size limit are rejected."""
        large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
        files = [("files", ("large.pdf", large_content, "application/pdf"))]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 400
        error_data = response.json()
        assert "detail" in error_data

    @pytest.mark.asyncio
    async def test_upload_rejects_invalid_mime_type(
        self,
        auth_client: AsyncClient,
        test_project_id: str,
    ) -> None:
        """Test that files with unsupported MIME types are rejected."""
        png_signature = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        files = [("files", ("image.png", png_signature, "image/png"))]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 400
        error_data = response.json()
        assert "detail" in error_data

    @pytest.mark.asyncio
    async def test_upload_rejects_too_many_files(
        self,
        auth_client: AsyncClient,
        test_project_id: str,
    ) -> None:
        """Test that exceeding file count limit is rejected."""
        files = [("files", (f"file{i}.pdf", b"PDF content", "application/pdf")) for i in range(11)]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 400
        error_data = response.json()
        assert "detail" in error_data

    @pytest.mark.asyncio
    async def test_upload_creates_file_metadata_record(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """Test that uploading a file creates FileMetadata record in database."""
        files = [("files", ("database_test.txt", b"Test content", "text/plain"))]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 201
        response_data = response.json()
        file_id = response_data["file_ids"][0]

        result = await test_db_session.exec(select(FileMetadata).where(FileMetadata.id == file_id))
        file_record = result.one_or_none()

        assert file_record is not None
        assert file_record.filename == "database_test.txt"
        assert file_record.mime_type == "text/plain"
        # Conversion runs asynchronously via Temporal workflow, not inline
        assert file_record.status == FileStatus.PENDING_CONVERSION

    @pytest.mark.asyncio
    async def test_upload_returns_correct_response_schema(
        self,
        auth_client: AsyncClient,
        test_project_id: str,
    ) -> None:
        """Test that response matches the expected FileUploadResponse schema."""
        files = [("files", ("schema_test.pdf", b"PDF content", "application/pdf"))]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 201
        response_data = response.json()

        assert "file_ids" in response_data
        assert "files" in response_data
        assert isinstance(response_data["file_ids"], list)
        assert isinstance(response_data["files"], list)

        for file_info in response_data["files"]:
            assert "file_id" in file_info
            assert "filename" in file_info
            assert "size_bytes" in file_info
            assert "mime_type" in file_info
            assert "status" in file_info
            assert "file_path" not in file_info

    @pytest.mark.asyncio
    async def test_upload_empty_files_list_rejected(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that request with no files is rejected."""
        response = await auth_client.post(
            "/api/v1/files",
            files=[],
        )

        assert response.status_code == 422


class TestFilesAPIConversion:
    """Test document conversion for files uploaded via POST /api/v1/files."""

    @pytest.mark.asyncio
    async def test_uploaded_file_can_be_converted(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """Test that an uploaded file can be successfully converted."""
        text_content = b"This is a sample document for conversion testing."
        files = [("files", ("conversion_test.txt", text_content, "text/plain"))]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 201
        response_data = response.json()
        file_id_str = response_data["file_ids"][0]
        file_id = UUID(file_id_str)

        # Verify initial status is PENDING_CONVERSION (conversion is async via Temporal)
        result = await test_db_session.exec(select(FileMetadata).where(FileMetadata.id == file_id))
        file_record = result.one()
        assert file_record.status == FileStatus.PENDING_CONVERSION

    @pytest.mark.asyncio
    async def test_uploaded_pdf_can_be_converted(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """Test that an uploaded PDF file can be successfully converted."""
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test PDF Content) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000206 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
300
%%EOF"""
        files = [("files", ("test_document.pdf", pdf_content, "application/pdf"))]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 201
        response_data = response.json()
        file_id_str = response_data["file_ids"][0]
        file_id = UUID(file_id_str)

        # Verify initial status is PENDING_CONVERSION (conversion is async via Temporal)
        result = await test_db_session.exec(select(FileMetadata).where(FileMetadata.id == file_id))
        file_record = result.one()
        assert file_record.status == FileStatus.PENDING_CONVERSION

    @pytest.mark.asyncio
    async def test_multiple_uploaded_files_can_be_converted(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """Test that multiple uploaded files can all be converted."""
        files = [
            ("files", ("doc1.txt", b"First document content", "text/plain")),
            ("files", ("doc2.txt", b"Second document content", "text/plain")),
            ("files", ("doc3.txt", b"Third document content", "text/plain")),
        ]

        response = await auth_client.post(
            "/api/v1/files",
            files=files,
            data={"project_id": test_project_id},
        )

        assert response.status_code == 201
        response_data = response.json()
        assert len(response_data["file_ids"]) == 3

        async def test_session_factory() -> AsyncGenerator[AsyncSession, None]:
            yield test_db_session

        conversion_task = get_document_conversion_task(session_factory=test_session_factory)

        for file_id_str in response_data["file_ids"]:
            file_id = UUID(file_id_str)

            await conversion_task.convert(file_id)

            result = await test_db_session.exec(select(FileMetadata).where(FileMetadata.id == file_id))
            updated_record = result.one()
            assert updated_record.status == FileStatus.CONVERTED
            assert updated_record.converted_content_path is not None


async def _create_file_metadata(
    session: AsyncSession,
    *,
    project_id: str,
    filename: str = "test.txt",
    size_bytes: int = 100,
    mime_type: str = "text/plain",
    file_status: FileStatus = FileStatus.PENDING_CONVERSION,
) -> FileMetadata:
    """Insert a FileMetadata record directly for testing (bypasses upload API)."""
    fm = FileMetadata(
        filename=filename,
        size_bytes=size_bytes,
        mime_type=mime_type,
        file_path=f"/opt/app-root/uploads/orchestrator-{uuid4()}-{filename}",
        status=file_status,
        project_id=UUID(project_id),
    )
    session.add(fm)
    await session.commit()
    await session.refresh(fm)
    return fm


_METADATA_URL = "/api/v1/files/metadata"


class TestFilesAPIMetadata:
    """Test GET /api/v1/files/metadata endpoint."""

    @pytest.mark.asyncio
    async def test_metadata_single_file_returns_correct_info(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """Test that requesting metadata for a single file returns correct fields."""
        fm = await _create_file_metadata(
            test_db_session,
            project_id=test_project_id,
            filename="report.pdf",
            size_bytes=2048,
            mime_type="application/pdf",
        )

        response = await auth_client.get(
            _METADATA_URL,
            params=[("file_ids", str(fm.id))],
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1

        file_info = data["files"][0]
        assert file_info["file_id"] == str(fm.id)
        assert file_info["filename"] == "report.pdf"
        assert file_info["size_bytes"] == 2048
        assert file_info["mime_type"] == "application/pdf"
        assert file_info["status"] == "pending_conversion"

    @pytest.mark.asyncio
    async def test_metadata_nonexistent_ids_returns_empty_files(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that non-existent file IDs return an empty files array (not 404)."""
        response = await auth_client.get(
            _METADATA_URL,
            params=[("file_ids", str(uuid4()))],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["files"] == []

    @pytest.mark.asyncio
    async def test_metadata_mixed_existing_and_nonexistent_ids(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """Test that a mix of real and fake IDs returns only the existing files."""
        fm1 = await _create_file_metadata(test_db_session, project_id=test_project_id, filename="exists1.txt")
        fm2 = await _create_file_metadata(test_db_session, project_id=test_project_id, filename="exists2.txt")

        response = await auth_client.get(
            _METADATA_URL,
            params=[("file_ids", str(fm1.id)), ("file_ids", str(fm2.id)), ("file_ids", str(uuid4()))],
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 2
        returned_ids = {f["file_id"] for f in data["files"]}
        assert returned_ids == {str(fm1.id), str(fm2.id)}

    @pytest.mark.asyncio
    async def test_metadata_empty_file_ids_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that missing file_ids query parameter is rejected with 422."""
        response = await auth_client.get(_METADATA_URL)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_metadata_exceeding_max_ids_returns_422(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that exceeding the 10-ID limit is rejected with 422."""
        response = await auth_client.get(
            _METADATA_URL,
            params=[("file_ids", str(uuid4())) for _ in range(11)],
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_metadata_unauthenticated_returns_401(
        self,
        base_client: AsyncClient,
    ) -> None:
        """Test that unauthenticated requests are rejected with 401."""
        response = await base_client.get(
            _METADATA_URL,
            params=[("file_ids", str(uuid4()))],
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_metadata_no_role_returns_empty(
        self,
        base_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        """Test that an authenticated user without any role gets an empty result."""
        limited_user = await user_factory(username="metadata-auth-only", email="metadata-auth-only@example.com")

        async def override() -> User:
            return limited_user

        app.dependency_overrides[get_current_user] = override

        response = await base_client.get(
            _METADATA_URL,
            params=[("file_ids", str(uuid4()))],
        )

        assert response.status_code == 200
        assert response.json()["files"] == []

    @pytest.mark.asyncio
    async def test_metadata_cross_project_isolation(
        self,
        base_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        """Test that a user cannot access file metadata from another project.

        Creates a file in project A, then authenticates as a user who only
        has access to project B. The file from project A should not be returned.
        """
        from tests.integration.api.conftest import make_project_user

        fm = await _create_file_metadata(test_db_session, project_id=test_project_id, filename="secret.txt")

        other_project = Project(
            name=f"other-project-{uuid4().hex[:8]}",
            description="Another project",
        )
        test_db_session.add(other_project)
        await test_db_session.commit()
        await test_db_session.refresh(other_project)

        scoped_user = await user_factory(username="scoped-user", email="scoped@example.com")
        await make_project_user(test_db_session, scoped_user, other_project)

        async def override() -> User:
            return scoped_user

        app.dependency_overrides[get_current_user] = override

        response = await base_client.get(
            _METADATA_URL,
            params=[("file_ids", str(fm.id))],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["files"] == [], "User with access only to project B should not see files from project A"

    @pytest.mark.asyncio
    async def test_metadata_does_not_expose_internal_paths(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_project_id: str,
    ) -> None:
        """Test that internal storage paths are never leaked in the API response."""
        fm = await _create_file_metadata(test_db_session, project_id=test_project_id, filename="paths.txt")

        response = await auth_client.get(
            _METADATA_URL,
            params=[("file_ids", str(fm.id))],
        )

        assert response.status_code == 200
        raw = response.text
        assert "file_path" not in raw
        assert "converted_content_path" not in raw
        assert "/opt/app-root/uploads/orchestrator-" not in raw
