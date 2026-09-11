"""Test auto-discovery of files audit handlers."""

import syntara.files.audit
from syntara.audit.discovery import discover_handlers
from syntara.files.audit.file_cleaned_up import FileCleanedUpEvent, FileCleanedUpHandler
from syntara.files.audit.file_converted import FileConvertedEvent, FileConvertedHandler
from syntara.files.audit.file_deleted import FileDeletedEvent, FileDeletedHandler
from syntara.files.audit.file_downloaded import FileDownloadedEvent, FileDownloadedHandler
from syntara.files.audit.file_integrity_failed import FileIntegrityFailedEvent, FileIntegrityFailedHandler
from syntara.files.audit.files_uploaded import FilesUploadedEvent, FilesUploadedHandler


def test_all_handlers_registered() -> None:
    """Verify that all files audit handlers are auto-discovered."""
    registry = discover_handlers(syntara.files.audit)

    assert len(registry) == 6, "Expected 6 handlers to be registered"
    assert FilesUploadedEvent in registry
    assert FileConvertedEvent in registry
    assert FileDownloadedEvent in registry
    assert FileDeletedEvent in registry
    assert FileIntegrityFailedEvent in registry
    assert FileCleanedUpEvent in registry

    assert isinstance(registry[FilesUploadedEvent], FilesUploadedHandler)
    assert isinstance(registry[FileConvertedEvent], FileConvertedHandler)
    assert isinstance(registry[FileDownloadedEvent], FileDownloadedHandler)
    assert isinstance(registry[FileDeletedEvent], FileDeletedHandler)
    assert isinstance(registry[FileIntegrityFailedEvent], FileIntegrityFailedHandler)
    assert isinstance(registry[FileCleanedUpEvent], FileCleanedUpHandler)
