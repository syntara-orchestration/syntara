"""Service layer for invocation business logic.

The InvocationService orchestrates:
- File validation and storage via FileManager
- Document conversion scheduling
- Invocation creation and management

Key design decisions:
- Uses FileManager for all file operations (encapsulation principle)
- Stores file_ids in context_data, not full file_metadata
- Orchestrates conversion and execution flow:
  * file_ids only (pre-converted): validate via FileManager, execute directly
  * Files uploaded at runtime: create FileMetadata, convert, then execute
  * Both file_ids AND uploads: validate file_ids, convert new files, execute with all
"""

from collections.abc import AsyncGenerator, Callable, Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from fastapi import UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from syntara.workflows.services.execution_service import ExecutionService

from syntara.agent_orchestrator.models import (
    Invocation,
    InvocationContextData,
    InvocationListResponse,
    InvocationMetadata,
    InvocationStatus,
)
from syntara.agent_orchestrator.models.request import CancellationResult
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import request_id_context_var
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.constants import CONTEXT_KEY_FILE_IDS
from syntara.core.database.session import get_db
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.files.file_manager import FileManager, get_file_manager
from syntara.files.models import FileMetadata
from syntara.invocations.audit.invocation_cancelled import InvocationCancellationResult, InvocationCancelledEvent
from syntara.invocations.audit.invocation_created import InvocationCreatedEvent

logger = structlog.stdlib.get_logger(__name__)


class InvocationService(BaseService):
    """Service for managing invocations.

    This service encapsulates business logic for invocations,
    separating it from HTTP/API concerns.
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        session_factory: Callable[[], AsyncGenerator[AsyncSession, None]] = get_db,
        file_manager_factory: Callable[[], FileManager] = get_file_manager,
        execution_service: "ExecutionService | None" = None,
    ) -> None:
        """Initialize service with database session.

        Args:
            session: Database session for queries
            user: Current authenticated user
            session_factory: Session factory for background tasks (defaults to get_db)
            file_manager_factory: Factory function for creating FileManager
            execution_service: Service for creating workflow executions

        """
        super().__init__(session, user)
        self.file_manager = file_manager_factory()
        self.session_factory = session_factory
        self.execution_service = execution_service

    async def _handle_file_uploads(self, files: list[UploadFile], project_id: UUID) -> list[FileMetadata]:
        if not files:
            return []

        return await self.file_manager.validate_and_save_files(files=files, project_id=project_id)

    async def _validate_file_ids(self, file_ids: list[str]) -> list[FileMetadata]:
        """Validate that file_ids reference existing FileMetadata records.

        Args:
            file_ids: List of file UUIDs (as strings) to validate

        Returns:
            List of FileMetadata records for the validated file_ids

        Raises:
            ValueError: If any file_ids are not found

        """
        if not file_ids:
            return []

        # Convert strings to UUIDs at the boundary
        uuid_ids = [UUID(fid) for fid in file_ids]
        existing_files = await self.file_manager.get_files_metadata(uuid_ids, self.session)
        found_ids = {str(f.id) for f in existing_files}
        missing = set(file_ids) - found_ids
        if missing:
            missing_ids = ", ".join(sorted(missing))
            msg = f"Files not found: {missing_ids}"
            raise SafeValueError(msg)

        return existing_files

    async def _start_builtin_workflows(
        self,
        invocation_id: UUID,
        file_ids: list[str] | None = None,
    ) -> None:
        """Start built-in workflows for this invocation.

        Starts the agent execution workflow and, if file_ids are provided,
        document conversion workflows. Workflows are started via Temporal
        (non-blocking RPC) so this returns quickly.

        Args:
            invocation_id: Invocation ID to execute
            file_ids: Optional file UUIDs to convert

        """
        if not self.execution_service:
            return

        from syntara.workflows.constants import (  # noqa: PLC0415
            BUILTIN_PROJECT_NAME,
            BUILTIN_WORKFLOW_AGENT_EXECUTION,
            BUILTIN_WORKFLOW_DOCUMENT_CONVERSION,
        )
        from syntara.workflows.exceptions import BuiltinWorkflowMissingError, WorkflowNotFoundError  # noqa: PLC0415

        if file_ids:
            for file_id in file_ids:
                try:
                    await self.execution_service.create_execution_by_name(
                        workflow_name=BUILTIN_WORKFLOW_DOCUMENT_CONVERSION,
                        input_data={"file_id": file_id},
                        project_name=BUILTIN_PROJECT_NAME,
                    )
                except WorkflowNotFoundError:
                    logger.warning("Builtin workflow 'Document Conversion' not found, skipping")

        try:
            await self.execution_service.create_execution_by_name(
                workflow_name=BUILTIN_WORKFLOW_AGENT_EXECUTION,
                input_data={
                    "invocation_id": str(invocation_id),
                    "actor_id": str(self.user.id),
                    "actor_username": self.user.username,
                    "actor_type": self.user.__principal_type__.value,
                },
                project_name=BUILTIN_PROJECT_NAME,
            )
        except WorkflowNotFoundError as exc:
            raise BuiltinWorkflowMissingError(BUILTIN_WORKFLOW_AGENT_EXECUTION) from exc

    async def create_invocation(
        self,
        prompt: str,
        session_id: str,
        project_id: UUID,
        context_data: dict[str, object] | None = None,
        files: list[UploadFile] | None = None,
    ) -> Invocation:
        """Create a new invocation.

        Orchestrates file handling and execution scheduling:
        - file_ids only (pre-converted): validate via FileManager, execute directly
        - Files uploaded at runtime: create FileMetadata, convert, then execute
        - Both file_ids AND uploads: validate file_ids, convert new files, execute with all
        - No files: execute directly

        Args:
            prompt: Natural language prompt
            session_id: Session identifier for multi-tenant isolation
            project_id: Project to associate this invocation with
            context_data: Optional context data (may contain file_ids)
            files: Optional list of file uploads (runtime upload)

        Returns:
            Created invocation

        Raises:
            ValidationError: If file validation fails (count, size, MIME type)
            ValueError: If file_ids reference non-existent files
            OSError: If file storage fails (disk full, permission denied, I/O error)

        """
        # Generate invocation ID upfront
        invocation_id = uuid4()

        # Parse context_data into typed model for validated access and audit.
        # The raw dict is kept for DB storage since model_dump() masks SecretStr
        # fields (callback_url, credential_id) which must be preserved in JSONB.
        final_context_data = dict(context_data or {})
        ctx = InvocationContextData.model_validate(final_context_data)

        # Capture request_id from context var and persist it in metadata
        # This allows the executor to restore the request_id when executing asynchronously
        request_id = request_id_context_var.get()
        if request_id is not None:
            # Ensure metadata exists
            if ctx.metadata is None:
                ctx.metadata = InvocationMetadata()
            ctx.metadata.request_id = str(request_id)
            # Update the raw dict to include the request_id in metadata
            if "metadata" not in final_context_data:
                final_context_data["metadata"] = {}
            final_context_data["metadata"]["request_id"] = str(request_id)  # type: ignore[index]

        # Validate existing file_ids reference real files
        if ctx.file_ids:
            await self._validate_file_ids(ctx.file_ids)
            logger.info(
                "Validated pre-uploaded files",
                file_count=len(ctx.file_ids),
                invocation_id=invocation_id,
            )

        # Process runtime file uploads
        new_file_metadata_list: list[FileMetadata] = await self._handle_file_uploads(files or [], project_id)
        new_file_ids: list[str] = [str(fm.id) for fm in new_file_metadata_list]

        # Persist new FileMetadata records to database (they need to exist before conversion)
        for metadata in new_file_metadata_list:
            self.session.add(metadata)

        # Merge all file_ids
        all_file_ids = ctx.file_ids + new_file_ids
        if all_file_ids:
            final_context_data[CONTEXT_KEY_FILE_IDS] = all_file_ids

        try:
            invocation = Invocation(
                id=invocation_id,
                prompt=prompt,
                created_by=self.user.id,
                session_id=session_id,
                project_id=project_id,
                status=InvocationStatus.CREATED,
                context_data=final_context_data,
            )
            self.session.add(invocation)
            await self.session.commit()

            logger.info(
                "Invocation created successfully",
                invocation_id=invocation_id,
                file_count=len(all_file_ids),
            )

            # Dispatch success audit event
            AuditEventDispatcher.dispatch(
                InvocationCreatedEvent(
                    invocation_id=invocation_id,
                    session_id=session_id,
                    file_ids=all_file_ids,
                    agent=ctx.agent,
                    model=ctx.model,
                    metadata=ctx.audit_safe_metadata(),
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )

        except Exception as e:
            # Database commit failed - cleanup saved files if any
            if new_file_metadata_list:
                logger.warning(
                    "Invocation creation failed, cleaning up saved files",
                    file_count=len(new_file_metadata_list),
                )
                saved_file_paths = [fm.file_path for fm in new_file_metadata_list]
                await self._cleanup_files_from_paths(saved_file_paths, invocation_id, context="after DB failure")

            # Dispatch failure audit event
            AuditEventDispatcher.dispatch(
                InvocationCreatedEvent(
                    invocation_id=invocation_id,
                    session_id=session_id,
                    file_ids=all_file_ids,
                    agent=ctx.agent,
                    model=ctx.model,
                    metadata=ctx.audit_safe_metadata(),
                    error_type=type(e).__name__,
                    activity_id=ctx.activity_id,
                    activity_name=ctx.activity_name,
                )
            )
            raise

        # Start builtin workflows AFTER successful commit
        await self._start_builtin_workflows(invocation_id, file_ids=new_file_ids or None)

        return invocation

    async def get_invocation(self, invocation_id: UUID) -> Invocation | None:
        """Get invocation by ID including result.

        NOTE: This method is primarily for TESTING and DEBUGGING purposes.
        Use this to inspect the actual agent responses during development.

        Args:
            invocation_id: UUID of the invocation

        Returns:
            Invocation with result data if found, None otherwise

        """
        return await self.session.get(Invocation, invocation_id)

    async def cancel_invocation(self, invocation_id: UUID, reason: str = "User cancelled") -> CancellationResult:
        """Cancel a running invocation.

        Args:
            invocation_id: UUID of the invocation to cancel
            reason: Reason for cancellation

        Returns:
            CancellationResult enum indicating the outcome of the cancellation attempt

        """
        invocation = await self.session.get(Invocation, invocation_id)

        if not invocation:
            logger.warning("Cancellation failed: Invocation not found", invocation_id=invocation_id)

            # Dispatch NOT_FOUND audit event (no activity context available)
            AuditEventDispatcher.dispatch(
                InvocationCancelledEvent(
                    invocation_id=invocation_id,
                    result=InvocationCancellationResult.NOT_FOUND,
                    reason=reason,
                )
            )
            return CancellationResult.NOT_FOUND

        # Extract activity context from invocation metadata for audit correlation
        context_data = invocation.context_data or {}
        activity_id: str | None = context_data.get("activity_id")  # type: ignore[assignment]
        activity_name: str | None = context_data.get("activity_name")  # type: ignore[assignment]

        # Check if invocation is in a cancellable state
        if invocation.status not in (InvocationStatus.CREATED, InvocationStatus.RUNNING):
            logger.warning(
                "Cancellation failed: Invocation not in cancellable state",
                invocation_id=invocation_id,
                status=invocation.status.value,
            )

            # Dispatch NOT_CANCELLABLE audit event
            AuditEventDispatcher.dispatch(
                InvocationCancelledEvent(
                    invocation_id=invocation_id,
                    result=InvocationCancellationResult.NOT_CANCELLABLE,
                    reason=reason,
                    current_status=invocation.status,
                    activity_id=activity_id,
                    activity_name=activity_name,
                )
            )
            return CancellationResult.NOT_CANCELLABLE

        # Update invocation with cancellation details using existing fields
        invocation.status = InvocationStatus.CANCELLED
        invocation.error_message = f"User cancelled: {reason}"
        invocation.completed_at = datetime.now(UTC)

        # Store cancellation metadata in checkpoint_data for debugging
        cancellation_data: dict[str, object] = {
            "cancelled_at": invocation.completed_at.isoformat(),
            "cancelled_by": str(self.user.id),
            "reason": reason,
        }

        # Merge with existing checkpoint_data if it exists
        if invocation.checkpoint_data:
            invocation.checkpoint_data.update(cancellation_data)
        else:
            invocation.checkpoint_data = cancellation_data

        # Clean up uploaded and converted files associated with this invocation
        cleaned_file_ids = await self._cleanup_invocation_files(invocation)

        # Note: Document conversion workflows will complete harmlessly even for
        # cancelled invocations. Execution workflow cancellation is handled by Temporal.

        try:
            await self.session.commit()

            logger.info("Invocation cancelled successfully", invocation_id=invocation_id, reason=reason)

            # Dispatch success audit event
            AuditEventDispatcher.dispatch(
                InvocationCancelledEvent(
                    invocation_id=invocation_id,
                    result=InvocationCancellationResult.SUCCESS,
                    reason=reason,
                    files_cleaned=cleaned_file_ids,
                    current_status=InvocationStatus.CANCELLED,
                    activity_id=activity_id,
                    activity_name=activity_name,
                )
            )
            return CancellationResult.SUCCESS

        except Exception as e:
            # Dispatch failure audit event
            AuditEventDispatcher.dispatch(
                InvocationCancelledEvent(
                    invocation_id=invocation_id,
                    result=InvocationCancellationResult.SUCCESS,
                    reason=reason,
                    files_cleaned=cleaned_file_ids,
                    error_type=type(e).__name__,
                    activity_id=activity_id,
                    activity_name=activity_name,
                )
            )
            raise

    async def _cleanup_files_from_paths(
        self, files_to_cleanup: list[str], invocation_id: UUID, *, context: str = ""
    ) -> None:
        """Clean up files from storage via the retriever (best-effort)."""
        if not files_to_cleanup:
            return

        logger.info(
            "Cleaning up files for invocation",
            file_count=len(files_to_cleanup),
            invocation_id=invocation_id,
            context=context,
        )
        try:
            retriever = self.file_manager.get_retriever()
            for file_path in files_to_cleanup:
                try:
                    await retriever.delete_file(file_path)
                    logger.info("Cleaned up file", file_path=file_path, context=context)
                except Exception:
                    logger.exception(
                        "Failed to cleanup file",
                        file_path=file_path,
                        invocation_id=invocation_id,
                        context=context,
                    )
        except Exception:
            logger.exception(
                "File cleanup failed for invocation",
                invocation_id=invocation_id,
            )

    async def _cleanup_invocation_files(self, invocation: Invocation) -> list[UUID]:
        """Clean up uploaded and converted files associated with an invocation.

        This method extracts file_ids from the invocation's context_data,
        retrieves FileMetadata records from the database, and cleans up
        both original uploaded files and converted files.

        Args:
            invocation: The invocation whose files should be cleaned up

        Note:
            This is a best-effort cleanup that won't raise exceptions if
            file deletion fails. Errors are logged for debugging.

        """
        ctx = InvocationContextData.model_validate(invocation.context_data or {})
        if not ctx.file_ids:
            logger.debug("No files to clean up for invocation", invocation_id=invocation.id)
            return []

        # Convert strings to UUIDs at the boundary
        file_ids = [UUID(fid) for fid in ctx.file_ids]

        # Get file metadata from database via FileManager
        file_metadata_records = await self.file_manager.get_files_metadata(file_ids, self.session)
        if not file_metadata_records:
            logger.debug("No FileMetadata records found for invocation", invocation_id=invocation.id)
            return []

        files_to_cleanup: list[str] = []
        for metadata in file_metadata_records:
            if metadata.file_path:
                files_to_cleanup.append(metadata.file_path)
            if metadata.converted_content_path:
                files_to_cleanup.append(metadata.converted_content_path)

        await self._cleanup_files_from_paths(files_to_cleanup, invocation.id, context="after invocation cancellation")

        return file_ids

    async def list_invocations(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> InvocationListResponse:
        """List invocations with filtering, sorting, and pagination.

        Args:
            limit: Maximum number of invocations to return (default 20)
            cursor: Cursor token for pagination
            sort: Sort parameter (e.g., "created_at", "-started_at")
            query_params_items: Raw query parameter items from request (for filtering)
            include_total: Whether to include total count in response
            allowed_projects: Optional project scope filter for authorization

        Returns:
            InvocationListResponse with invocations, pagination metadata, and optional total

        """
        # Use unified list_resources method (fields read from model automatically)
        return await self.list_resources(
            model=Invocation,
            response_type=InvocationListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort or "-created_at",  # Default DESC sort if none provided
            query_params_items=query_params_items,
            include_total=include_total,
            allowed_projects=allowed_projects,
        )
