"""FileManager for file upload handling.

This module provides the main FileManager class for handling file uploads,
including validation, storage, and metadata generation.

The FileManager is the single source of truth for all FileMetadata operations.
All components (DocumentConversionTask, InvocationService, UploadedFileRetriever)
must access FileMetadata records through FileManager methods, not via direct
database queries (encapsulation principle).
"""

import hashlib
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import structlog
from fastapi import UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.config.base import get_settings
from syntara.core.exceptions import SafeValueError
from syntara.files import storage, validators
from syntara.files.audit.file_integrity_failed import FileIntegrityFailedEvent
from syntara.files.audit.files_uploaded import FilesUploadedEvent
from syntara.files.exceptions import FileError, FileIntegrityError, FileStorageUnavailableError, FileValidationError
from syntara.files.models import FileMetadata, FileStatus
from syntara.files.retrievers.base import BaseRetriever
from syntara.files.retrievers.s3 import S3FileRetriever
from syntara.files.storage import sanitize_filename

logger = structlog.stdlib.get_logger(__name__)

UNKNOWN_FILENAME = "unknown"


class FileManager:
    """Manager for file upload operations using S3-compatible storage.

    The FileManager is the single source of truth for all FileMetadata operations.
    All components (DocumentConversionTask, InvocationService, UploadedFileRetriever)
    must access FileMetadata records through FileManager methods, not via direct
    database queries (encapsulation principle).

    If S3 is not configured (APP_S3_ENDPOINT_URL not set), the FileManager
    initializes without a retriever and file operations return 503.

    Attributes:
        settings: Application settings for validation limits

    """

    def __init__(self) -> None:
        """Initialize FileManager with application settings."""
        self.settings = get_settings()
        self._retriever: BaseRetriever | None = None

        if self.settings.s3_endpoint_url is not None:
            self._retriever = S3FileRetriever(
                endpoint_url=self.settings.s3_endpoint_url,
                bucket_name=self.settings.s3_bucket_name,
                region_name=self.settings.s3_region,
                aws_access_key_id=self.settings.s3_access_key_id,
                aws_secret_access_key=self.settings.s3_secret_access_key,
                verify_ssl=self.settings.s3_verify_ssl,
                ca_bundle=self.settings.s3_ca_bundle,
                use_path_style=self.settings.s3_use_path_style,
            )
        else:
            logger.warning(
                "S3 not configured — file uploads will be unavailable",
                hint="Set APP_S3_ENDPOINT_URL to enable file storage",
            )

    @property
    def s3_configured(self) -> bool:
        """Whether S3 storage is configured and available."""
        return self._retriever is not None

    def get_retriever(self) -> BaseRetriever:
        """Return the S3 retriever.

        Raises:
            FileStorageUnavailableError: If S3 is not configured (maps to 503)

        """
        if self._retriever is None:
            msg = "File storage is not configured. An administrator must set APP_S3_ENDPOINT_URL."
            raise FileStorageUnavailableError(msg)
        return self._retriever

    async def stream_file_with_integrity_check(self, file_metadata: FileMetadata) -> AsyncGenerator[bytes]:
        """Stream file content while computing SHA-256 incrementally.

        Buffers one chunk behind so the hash can be verified before the
        last chunk is yielded.  On mismatch the final chunk is withheld,
        making the response shorter than Content-Length — every HTTP client
        treats that as a failed download.  Legacy files without a stored
        content_hash skip verification and stream without buffering.

        Args:
            file_metadata: FileMetadata with file_path and content_hash

        Yields:
            File content in chunks

        Raises:
            FileIntegrityError: If computed hash doesn't match stored hash

        """
        retriever = self.get_retriever()

        if file_metadata.content_hash is None:
            async for chunk in retriever.stream_file(file_metadata.file_path):
                yield chunk
            return

        hasher = hashlib.sha256()
        pending: bytes | None = None

        async for chunk in retriever.stream_file(file_metadata.file_path):
            hasher.update(chunk)
            if pending is not None:
                yield pending
            pending = chunk

        actual_hash = hasher.hexdigest()
        if actual_hash != file_metadata.content_hash:
            logger.critical(
                "File integrity check failed",
                file_id=str(file_metadata.id),
                filename=file_metadata.filename,
                storage_backend="s3",
                expected_hash=file_metadata.content_hash,
                actual_hash=actual_hash,
            )
            AuditEventDispatcher.dispatch(
                FileIntegrityFailedEvent(
                    file_id=file_metadata.id,
                    filename=file_metadata.filename,
                    storage_backend="s3",
                    expected_hash=file_metadata.content_hash,
                    actual_hash=actual_hash,
                ),
            )
            msg = (
                f"File integrity check failed for {file_metadata.id}: "
                f"expected {file_metadata.content_hash}, got {actual_hash}"
            )
            raise FileIntegrityError(msg)

        if pending is not None:
            yield pending

    @staticmethod
    async def _stream_upload_file(
        header: bytes, file: UploadFile, chunk_size: int = 1024 * 1024
    ) -> AsyncGenerator[bytes]:
        """Yield header bytes then stream remaining content from the UploadFile.

        Args:
            header: Already-read header bytes (from MIME detection)
            file: UploadFile positioned after the header
            chunk_size: Size of subsequent read chunks (default 1 MB)

        Yields:
            File content chunks — header first, then remaining data.

        """
        if header:
            yield header
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            yield chunk

    async def _validate_and_stream_file(
        self,
        file: UploadFile,
        retriever: BaseRetriever,
        project_id: UUID,
    ) -> tuple[FileMetadata, str]:
        """Validate, stream, and hash a single file to S3.

        Returns:
            Tuple of (FileMetadata, saved S3 path).

        """
        safe_filename = sanitize_filename(file.filename) if file.filename else UNKNOWN_FILENAME
        header, mime_type = await validators.validate_single_file(file, self.settings)

        file_id = uuid4()
        hasher = hashlib.sha256()

        async def _hashing_stream() -> AsyncGenerator[bytes]:
            async for chunk in self._stream_upload_file(header, file):
                hasher.update(chunk)
                yield chunk

        file_path, file_size_bytes = await storage.save_file_stream(
            _hashing_stream(),
            safe_filename,
            str(file_id),
            retriever,
        )

        metadata = FileMetadata(
            id=file_id,
            filename=safe_filename,
            size_bytes=file_size_bytes,
            mime_type=mime_type,
            file_path=file_path,
            content_hash=hasher.hexdigest(),
            status=FileStatus.PENDING_CONVERSION,
            project_id=project_id,
        )

        logger.info("File processed successfully", filename=safe_filename, file_id=file_id)
        return metadata, file_path

    @staticmethod
    async def _cleanup_saved_files(retriever: BaseRetriever, saved_file_paths: list[str]) -> None:
        """Delete already-saved S3 objects on failure."""
        for path in saved_file_paths:
            try:
                await retriever.delete_file(path)
            except (OSError, FileError):
                logger.warning("Cleanup failed for saved file", path=path, exc_info=True)

    async def validate_and_save_files(
        self,
        files: list[UploadFile],
        project_id: UUID,
    ) -> list[FileMetadata]:
        """Validate and save uploaded files with streaming and transactional cleanup.

        Processes one file at a time to keep memory usage constant:
        1. Validate file count
        2. For each file: validate size → read header for MIME detection →
           stream content through incremental SHA-256 hash → S3 multipart upload
        3. Cleanup saved files if any step fails

        Memory usage is O(chunk_size) per file regardless of file size.

        Note: Database persistence is handled by the caller. This method
        returns in-memory FileMetadata objects that should be added to
        a database session and committed.

        Args:
            files: List of uploaded files
            project_id: Project to associate files with

        Returns:
            List of FileMetadata objects with file information (not yet persisted)

        Raises:
            FileValidationError: If file validation fails (count, size, or MIME type)
            FileStorageUnavailableError: If S3 is not configured (503)
            OSError: If storage operation fails

        """
        logger.info(
            "Starting file upload processing",
            file_count=len(files),
        )

        try:
            await validators.validate_file_count(files, self.settings.file_upload_max_files)
        except FileValidationError:
            logger.warning("File validation failed")
            AuditEventDispatcher.dispatch(
                FilesUploadedEvent(
                    file_count=len(files),
                    total_size_bytes=0,
                    file_details=[{"filename": sanitize_filename(f.filename or UNKNOWN_FILENAME)} for f in files],
                    error_type="FileValidationError",
                )
            )
            raise

        retriever = self.get_retriever()

        file_metadata_list: list[FileMetadata] = []
        saved_file_paths: list[str] = []

        # Each file is validated and streamed to S3 one at a time to keep
        # memory usage constant (O(chunk_size) instead of O(total_file_size)).
        # If file N+1 fails validation or storage, all files saved during
        # *this request* (saved_file_paths) are deleted from S3 before the
        # error propagates.  Previously uploaded files are never touched —
        # each call creates new S3 objects with fresh UUIDs.
        file_details_for_audit = [{"filename": sanitize_filename(f.filename or UNKNOWN_FILENAME)} for f in files]

        cleaned_up = False
        try:
            for file in files:
                try:
                    metadata, file_path = await self._validate_and_stream_file(file, retriever, project_id)
                except FileValidationError:
                    logger.warning("File validation failed")
                    await self._cleanup_saved_files(retriever, saved_file_paths)
                    cleaned_up = True
                    AuditEventDispatcher.dispatch(
                        FilesUploadedEvent(
                            file_count=len(files),
                            total_size_bytes=0,
                            file_details=file_details_for_audit,
                            error_type="FileValidationError",
                        )
                    )
                    raise

                saved_file_paths.append(file_path)
                file_metadata_list.append(metadata)

        except FileValidationError:
            raise
        except (OSError, FileError) as e:
            logger.exception(
                "Storage failure during file processing, cleaning up saved files",
                saved_file_count=len(saved_file_paths),
            )
            await self._cleanup_saved_files(retriever, saved_file_paths)
            cleaned_up = True

            AuditEventDispatcher.dispatch(
                FilesUploadedEvent(
                    file_count=len(files),
                    total_size_bytes=0,
                    file_details=file_details_for_audit,
                    error_type=type(e).__name__,
                )
            )

            raise
        finally:
            # CancelledError and other BaseExceptions bypass the except blocks.
            # Clean up any already-saved S3 objects if the batch did not complete.
            if not cleaned_up and saved_file_paths and len(file_metadata_list) != len(files):
                await self._cleanup_saved_files(retriever, saved_file_paths)

        logger.info(
            "All files processed successfully",
            file_count=len(file_metadata_list),
        )

        file_details = [
            {
                "file_id": str(fm.id),
                "filename": fm.filename,
                "mime_type": fm.mime_type,
                "size_bytes": fm.size_bytes,
                "storage_backend": "s3",
            }
            for fm in file_metadata_list
        ]
        total_size = sum(fm.size_bytes for fm in file_metadata_list)

        AuditEventDispatcher.dispatch(
            FilesUploadedEvent(
                file_count=len(file_metadata_list),
                total_size_bytes=total_size,
                file_details=file_details,
            )
        )

        return file_metadata_list

    async def get_file_metadata(
        self,
        file_id: UUID,
        session: AsyncSession,
    ) -> FileMetadata | None:
        """Get FileMetadata record by file_id.

        Args:
            file_id: UUID of the file to retrieve
            session: Database session

        Returns:
            FileMetadata record if found, None otherwise

        """
        return await session.get(FileMetadata, file_id)

    async def get_files_metadata(
        self,
        file_ids: list[UUID],
        session: AsyncSession,
        *,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> list[FileMetadata]:
        """Get multiple FileMetadata records by file_ids.

        Args:
            file_ids: List of file UUIDs to retrieve
            session: Database session
            allowed_projects: Project-scoped access filter; when provided and not
                all_projects, only files belonging to the user's accessible projects
                are returned.

        Returns:
            List of FileMetadata records (may be fewer than requested if some not found)

        """
        if not file_ids:
            return []

        if allowed_projects is not None and not allowed_projects.all_projects and not allowed_projects.project_ids:
            return []
        # FileMetadata.id is inherited from BaseResource, so type checker doesn't see in_() method
        statement = select(FileMetadata).where(FileMetadata.id.in_(file_ids))  # type: ignore[attr-defined]

        if allowed_projects is not None and not allowed_projects.all_projects:
            statement = statement.where(
                FileMetadata.project_id.in_(allowed_projects.project_ids),  # type: ignore[attr-defined]
            )

        result = await session.exec(statement)
        return list(result.all())

    async def update_file_status(
        self,
        file_id: UUID,
        status: FileStatus,
        session: AsyncSession,
        *,
        converted_content_path: str | None = None,
        conversion_error: str | None = None,
    ) -> FileMetadata:
        """Update file conversion status in database.

        Used by DocumentConversionTask to update status after conversion.

        Args:
            file_id: UUID of the file to update
            status: New status (CONVERTING, CONVERTED, CONVERSION_FAILED)
            session: Database session
            converted_content_path: Path to converted markdown (if successful)
            conversion_error: Error message (if failed)

        Returns:
            Updated FileMetadata record

        Raises:
            ValueError: If file not found

        """
        file_metadata = await session.get(FileMetadata, file_id)
        if not file_metadata:
            msg = f"File not found: {file_id}"
            raise SafeValueError(msg)

        file_metadata.status = status
        if converted_content_path is not None:
            file_metadata.converted_content_path = converted_content_path
        if conversion_error is not None:
            file_metadata.conversion_error = conversion_error

        session.add(file_metadata)
        await session.commit()

        logger.info(
            "File status updated",
            file_id=file_id,
            status=status.value,
        )

        return file_metadata


# ===================================================
# Lazy singleton — instantiated on first get_file_manager() call
# to avoid import-time crashes when S3 env vars are missing.
# ---------------------------------------------------
_file_manager: FileManager | None = None


def get_file_manager() -> FileManager:
    """Get the FileManager singleton (lazy-initialized).

    Returns:
        FileManager: Shared FileManager instance

    """
    global _file_manager  # noqa: PLW0603
    if _file_manager is None:
        _file_manager = FileManager()
    return _file_manager


# ===================================================


__all__ = [
    "FileManager",
    "get_file_manager",
]
