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

from collections.abc import AsyncGenerator, Callable
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
    InvocationMetadata,
    InvocationStatus,
)
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import request_id_context_var
from syntara.core.constants import CONTEXT_KEY_FILE_IDS
from syntara.core.database.session import get_db
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.files.file_manager import FileManager, get_file_manager
from syntara.files.models import FileMetadata
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
