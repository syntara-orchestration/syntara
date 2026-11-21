"""Files API endpoints for v1.

This module provides the standalone file upload endpoint that creates
FileMetadata records in the database for later use in agent invocations.

Document conversion is triggered automatically for each uploaded file
via a builtin Temporal workflow.
"""

from collections.abc import AsyncGenerator
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import (
    Depends,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import VisibilityResult
from syntara.core.database.session import get_db
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.syntara_router import NO_PERMISSION, SyntaraRouter
from syntara.files.audit.file_deleted import FileDeletedEvent
from syntara.files.audit.file_downloaded import FileDownloadedEvent
from syntara.files.file_manager import FileManager, get_file_manager
from syntara.files.health import FileStorageStatus, check_file_storage_health
from syntara.files.models.file_metadata import FileMetadata, FileStatus
from syntara.files.storage import sanitize_filename
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

router = SyntaraRouter(prefix="/files", tags=["Files"])
logger = structlog.stdlib.get_logger(__name__)

_files_perm_upload = PermissionChecker(
    "files",
    "upload",
    form_project_field="project_id",
)

# ============================================================================
# Dependency Injection Providers
# ============================================================================


def _files_binary_format(schema: dict[str, Any]) -> None:
    items = schema.get("items")
    if isinstance(items, dict):
        items["format"] = "binary"


class UploadFilesBody(BaseModel):
    """Request body for POST /files endpoint."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    files: list[UploadFile] = Field(
        description="Files to upload (1-10 files, max 10MB each)",
        json_schema_extra=_files_binary_format,
    )
    project_id: UUID = Field(description="Project to associate files with")


class FileUploadInfo(BaseModel):
    """Response model for individual file upload information.

    Security Note:
        file_path is intentionally excluded from this model to prevent
        exposing internal filesystem paths in API responses.
    """

    file_id: UUID = Field(
        title="File ID", description="Unique file identifier (UUID)", examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    filename: str = Field(description="Original filename from upload", examples=["document.pdf"])
    size_bytes: int = Field(description="File size in bytes", examples=[524288])
    mime_type: str = Field(
        title="MIME Type", description="Detected MIME type of the file", examples=["application/pdf"]
    )
    status: FileStatus = Field(description="Processing status (pending_conversion)")
    is_project_deleted: bool | None = Field(
        default=None,
        description=(
            "True when the owning project has been soft-deleted; the file is "
            "retained as an orphan. Null when not computed (e.g. upload response)."
        ),
    )


class FileUploadResponse(BaseModel):
    """Response model for POST /api/v1/files endpoint."""

    file_ids: list[UUID] = Field(
        title="File IDs",
        description="List of file IDs for later reference in invocations",
        examples=[["550e8400-e29b-41d4-a716-446655440000"]],
    )
    files: list[FileUploadInfo] = Field(description="Metadata for each uploaded file")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Upload files (design time)",
    description="Upload files independently of invocations for later use in agent execution. "
    "Returns file_ids that can be stored in workflow configuration and passed to invocations. "
    "Files are validated, stored, and queued for document conversion.",
    dependencies=[Depends(_files_perm_upload)],
    operation_id="upload_files",
    response_description="Files uploaded successfully",
    openapi_extra={
        "responses": {
            "201": {
                "content": {
                    "application/json": {
                        "examples": {
                            "singleFile": {
                                "summary": "Single file upload",
                                "value": {
                                    "file_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                                    "files": [
                                        {
                                            "file_id": "550e8400-e29b-41d4-a716-446655440000",
                                            "filename": "document.pdf",
                                            "size_bytes": 524288,
                                            "mime_type": "application/pdf",
                                            "status": "pending_conversion",
                                        }
                                    ],
                                },
                            }
                        }
                    }
                }
            }
        }
    },
)
async def upload_files(
    db: Annotated[AsyncSession, Depends(get_db)],
    file_manager: Annotated[FileManager, Depends(get_file_manager)],
    current_user: Annotated[User, Depends(get_current_user)],
    body: Annotated[UploadFilesBody, Form(media_type="multipart/form-data")],
    temporal_service: Annotated[TemporalExecutionService | None, Depends(get_temporal_execution_service)],
) -> FileUploadResponse:
    """Upload files for later use in agent invocations.

    This endpoint allows uploading files at workflow design time. Files are:
    1. Validated (size, type, count)
    2. Stored on the filesystem
    3. Registered in the FileMetadata database table
    4. Queued for document conversion (via builtin Temporal workflow)

    Args:
        db: Database session (dependency injected)
        file_manager: FileManager instance (dependency injected)
        current_user: Current authenticated user
        body: Upload body containing the list of files (multipart/form-data)
        temporal_service: Temporal execution service (injected by FastAPI)

    Returns:
        FileUploadResponse with file_ids and file metadata

    Raises:
        HTTPException: 400 for validation errors, 500 for storage failures

    """
    # Validate at least one file is provided
    if not body.files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be provided",
        )

    # Validate and save files (returns in-memory FileMetadata objects)
    file_metadata_list = await file_manager.validate_and_save_files(body.files, body.project_id)

    for metadata in file_metadata_list:
        db.add(metadata)

    await db.commit()

    # Refresh to get database-assigned values
    for metadata in file_metadata_list:
        await db.refresh(metadata)

    # Start builtin document conversion workflows via Temporal (non-blocking RPC)
    if temporal_service:
        exec_service = ExecutionService(db, current_user, temporal_service=temporal_service)

        from syntara.workflows.constants import (  # noqa: PLC0415
            BUILTIN_PROJECT_NAME,
            BUILTIN_WORKFLOW_DOCUMENT_CONVERSION,
        )

        for metadata in file_metadata_list:
            try:
                await exec_service.create_execution_by_name(
                    workflow_name=BUILTIN_WORKFLOW_DOCUMENT_CONVERSION,
                    input_data={"file_id": str(metadata.id)},
                    project_name=BUILTIN_PROJECT_NAME,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Document conversion dispatch failed, file uploaded but conversion skipped",
                    file_id=str(metadata.id),
                    exc_info=True,
                )

    # Build response (exclude file_path for security)
    file_upload_infos = [
        FileUploadInfo(
            file_id=metadata.id,
            filename=metadata.filename,
            size_bytes=metadata.size_bytes,
            mime_type=metadata.mime_type,
            status=metadata.status,
        )
        for metadata in file_metadata_list
    ]

    return FileUploadResponse(
        file_ids=[m.id for m in file_metadata_list],
        files=file_upload_infos,
    )


_files_perm_download = PermissionChecker(
    "files",
    "download",
    resource_model=FileMetadata,
    resource_id_param="file_id",
)

_files_perm_delete = PermissionChecker(
    "files",
    "delete",
    resource_model=FileMetadata,
    resource_id_param="file_id",
)


class FileDetailResponse(BaseModel):
    """Response model for GET /api/v1/files/{file_id} endpoint."""

    file_id: UUID = Field(
        title="File ID", description="Unique file identifier (UUID)", examples=["550e8400-e29b-41d4-a716-446655440000"]
    )
    filename: str = Field(description="Original filename from upload", examples=["document.pdf"])
    size_bytes: int = Field(description="File size in bytes", examples=[524288])
    mime_type: str = Field(
        title="MIME Type", description="Detected MIME type of the file", examples=["application/pdf"]
    )
    status: FileStatus = Field(description="Current processing status")
    conversion_error: str | None = Field(
        default=None, description="Error message if conversion failed", examples=[None]
    )
    is_project_deleted: bool = Field(
        description=(
            "True when the owning project has been soft-deleted; the file is "
            "retained as an orphan. Project-scoped files:delete cannot remove "
            "orphans after soft-delete; only system-scope files:delete with a "
            "known file UUID can."
        ),
    )


class FilesMetadataResponse(BaseModel):
    """Response model for GET /files/metadata endpoint."""

    files: list[FileUploadInfo] = Field(
        description="Metadata for each found file (missing IDs are silently omitted)",
    )


class FileStorageStatusResponse(BaseModel):
    """Response model for GET /files/storage_status endpoint."""

    status: FileStorageStatus = Field(
        description="Availability of the object storage backend. Anything other than 'ok' means file uploads "
        "are unavailable.",
        examples=["ok"],
    )


@router.get(
    "/storage_status",
    summary="Get File Storage Status",
    description="Report whether the S3-compatible object storage backend is configured and reachable. "
    "Clients use this to disable file upload controls when uploads cannot succeed. "
    "Object storage is not a hard dependency of the API, so this is reported here rather than "
    "on the readiness probe.",
    dependencies=[NO_PERMISSION],
    operation_id="get_file_storage_status",
)
async def get_file_storage_status(
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
) -> FileStorageStatusResponse:
    """Report object storage availability.

    Permission-free beyond authentication: this exposes deployment
    configuration state rather than any project-scoped resource, and every
    authenticated user needs it to render upload controls correctly.
    """
    return FileStorageStatusResponse(status=await check_file_storage_health())


_files_visibility = VisibilityFilter("files", "download")


@router.get(
    "/metadata",
    summary="Get files metadata (batch)",
    description="Retrieve metadata for one or more files by their IDs. "
    "Returns file information (filename, size, MIME type, status) without file content.",
    operation_id="get_files_metadata",
)
async def get_files_metadata(
    file_ids: Annotated[
        list[UUID],
        Query(min_length=1, max_length=10, title="File IDs", description="List of file IDs to retrieve metadata for"),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_manager: Annotated[FileManager, Depends(get_file_manager)],
    visibility: Annotated[VisibilityResult, Depends(_files_visibility)],
) -> FilesMetadataResponse:
    """Retrieve metadata for multiple files by their IDs."""
    metadata_list = await file_manager.get_files_metadata(
        file_ids,
        db,
        allowed_projects=visibility.to_allowed_projects(),
    )
    project_ids = {m.project_id for m in metadata_list}
    project_deleted_map = await file_manager.batch_is_project_deleted(project_ids, db)
    files_info = [
        FileUploadInfo(
            file_id=m.id,
            filename=m.filename,
            size_bytes=m.size_bytes,
            mime_type=m.mime_type,
            status=m.status,
            is_project_deleted=project_deleted_map.get(m.project_id, True),
        )
        for m in metadata_list
    ]
    return FilesMetadataResponse(files=files_info)


@router.get(
    "/{file_id}/download",
    summary="Download file",
    description="Download a file by its ID. Serves the file from whichever storage backend it was uploaded to.",
    dependencies=[Depends(_files_perm_download)],
    operation_id="download_file",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "File content as binary stream",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "contentMediaType": "application/octet-stream"},
                },
            },
        },
    },
)
async def download_file(
    file_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    file_manager: Annotated[FileManager, Depends(get_file_manager)],
) -> StreamingResponse:
    """Download a file by ID from S3 storage.

    Authorization is handled entirely by PermissionChecker (dependency),
    which verifies files:download permission via project-scoped Rego policies.

    Args:
        file_id: UUID of the file to download
        db: Database session
        file_manager: FileManager instance

    Returns:
        StreamingResponse with file content, MIME type, and Content-Disposition

    Raises:
        HTTPException: 404 if file not found

    """
    metadata = await file_manager.get_file_metadata(file_id, db)
    if metadata is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file could not be found",
        )

    async def _stream_and_audit() -> AsyncGenerator[bytes]:
        """Wrap the streaming download with audit event dispatch.

        Emits a FileDownloadedEvent after streaming completes (or fails).
        Tracks bytes yielded to detect client disconnects — GeneratorExit
        inherits from BaseException and bypasses ``except Exception``, so
        a bytes-vs-expected comparison in ``finally`` is used instead.
        """
        download_error: str | None = None
        bytes_yielded = 0
        try:
            async for chunk in file_manager.stream_file_with_integrity_check(metadata):
                yield chunk
                bytes_yielded += len(chunk)
        except Exception as e:
            download_error = type(e).__name__
            raise
        finally:
            if download_error is None and bytes_yielded < metadata.size_bytes:
                download_error = "ClientDisconnect"
            AuditEventDispatcher.dispatch(
                FileDownloadedEvent(
                    file_id=metadata.id,
                    filename=metadata.filename,
                    mime_type=metadata.mime_type,
                    size_bytes=metadata.size_bytes,
                    storage_backend="s3",
                    error_type=download_error,
                ),
            )

    safe_name = sanitize_filename(metadata.filename)
    return StreamingResponse(
        _stream_and_audit(),
        media_type=metadata.mime_type,
        headers={
            "content-disposition": f'attachment; filename="{safe_name}"',
            "content-length": str(metadata.size_bytes),
            "x-content-type-options": "nosniff",
        },
    )


@router.get(
    "/{file_id}",
    summary="Get File Details",
    description="Retrieve metadata and conversion status for a single file by its ID. "
    "Use this endpoint to poll for conversion status after upload.",
    dependencies=[Depends(_files_perm_download)],
    operation_id="get_file_details",
)
async def get_file_details(
    file_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    file_manager: Annotated[FileManager, Depends(get_file_manager)],
) -> FileDetailResponse:
    """Retrieve metadata and conversion status for a single file.

    Args:
        file_id: UUID of the file
        db: Database session
        file_manager: FileManager instance

    Returns:
        FileDetailResponse with file metadata, status, and any conversion error

    Raises:
        HTTPException: 404 if file not found

    """
    metadata = await file_manager.get_file_metadata(file_id, db)
    if metadata is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file could not be found",
        )

    return FileDetailResponse(
        file_id=metadata.id,
        filename=metadata.filename,
        size_bytes=metadata.size_bytes,
        mime_type=metadata.mime_type,
        status=metadata.status,
        conversion_error=metadata.conversion_error,
        is_project_deleted=await file_manager.is_project_deleted(metadata.project_id, db),
    )


@router.delete(
    "/{file_id}",
    summary="Delete file",
    description="Permanently delete a file and its stored content. "
    "After a project is soft-deleted, project-scoped files:delete cannot "
    "authorize orphan cleanup (the project no longer resolves). Only "
    "system-scope files:delete can remove an orphan, and only when the "
    "caller already knows the file UUID.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_204_NO_CONTENT: {"description": "File deleted successfully"}},
    dependencies=[Depends(_files_perm_delete)],
    operation_id="delete_file",
)
async def delete_file(
    file_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    file_manager: Annotated[FileManager, Depends(get_file_manager)],
) -> None:
    """Delete a file by ID from storage and the database.

    Authorization is handled by PermissionChecker (files:delete). After
    project soft-delete, project-scoped files:delete does not match (the
    project is filtered out), so only system-scope files:delete with a
    known UUID can remove an orphan.

    Raises:
        HTTPException: 404 if file not found

    """
    existing = await file_manager.get_file_metadata(file_id, db)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file could not be found",
        )

    delete_error: str | None = None
    try:
        await file_manager.delete_file(file_id, db)
    except SafeValueError as e:
        # Race: deleted between lookup and delete
        delete_error = type(e).__name__
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file could not be found",
        ) from e
    except Exception as e:
        delete_error = type(e).__name__
        raise
    finally:
        AuditEventDispatcher.dispatch(
            FileDeletedEvent(
                file_id=file_id,
                filename=existing.filename,
                project_id=existing.project_id,
                storage_backend="s3",
                error_type=delete_error,
            ),
        )
