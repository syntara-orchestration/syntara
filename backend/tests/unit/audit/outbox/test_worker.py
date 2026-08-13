"""Unit tests for AuditEventWriter."""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from opentelemetry.sdk._logs.export import LogRecordExportResult
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.models.audit_event import AuditEvent, EventCategory
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.outbox.models import AuditEventSource, AuditOutboxRecord
from syntara.audit.outbox.worker import (
    _OTEL_DISPATCH_RETRY_MESSAGE,
    AuditOutboxWorker,
    _build_otel_log_record,
    _handle_crud_audit_records,
    publish_outbox_events,
)
from syntara.audit.sanitization import REDACTED

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_event(**overrides: object) -> AuditEvent:
    """Create a minimal AuditEvent for testing."""
    defaults = {
        "event_category": EventCategory.SYSTEM_OPERATION,
        "event_action": "test_action",
        "source_component": "test",
        "event_message": "test message",
        "structured_data": AuditContextData(data_type="test"),
    }
    defaults.update(overrides)
    return AuditEvent(**defaults)


# ------------------------------------------------------------------ #
# Enqueue
# ------------------------------------------------------------------ #


class TestAuditEventWriterEnqueue:
    """Test AuditEventWriter.enqueue method."""

    @pytest.mark.asyncio
    async def test_enqueue_creates_task(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that enqueue creates an asyncio task and persists the event."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )
        event = _make_event()

        worker.write_to_outbox(event)
        assert len(worker._pending) == 1

        await worker.drain()
        assert len(worker._pending) == 0

    @pytest.mark.asyncio
    async def test_enqueue_task_removed_on_completion(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that completed tasks are removed from pending set."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )
        event = _make_event()

        worker.write_to_outbox(event)
        assert len(worker._pending) == 1

        await worker.drain()

        assert len(worker._pending) == 0

    def test_enqueue_without_event_loop_logs_warning(self) -> None:
        """Test that enqueue logs a warning when no event loop is running."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=MagicMock(),
            write_session_factory=MagicMock(),
            coordinate=True,
        )
        event = _make_event()

        with (
            patch("asyncio.create_task", side_effect=RuntimeError("no running event loop")),
            patch("syntara.audit.outbox.worker.logger") as mock_logger,
        ):
            worker.write_to_outbox(event)

            mock_logger.warning.assert_called_once_with(
                "audit_event_write_skipped_no_loop",
                event_id=str(event.event_id),
            )

        assert len(worker._pending) == 0

    @pytest.mark.asyncio
    async def test_enqueue_multiple_events(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test enqueueing multiple events creates separate tasks."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )

        events = [_make_event() for _ in range(3)]
        for event in events:
            worker.write_to_outbox(event)

        assert len(worker._pending) == 3

        await worker.drain()
        assert len(worker._pending) == 0


# ------------------------------------------------------------------ #
# Write
# ------------------------------------------------------------------ #


class TestAuditEventWriterWrite:
    """Test AuditEventWriter._write method."""

    @pytest.mark.asyncio
    async def test_write_persists_record(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that _write creates an outbox record and commits it."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )
        event = _make_event()

        await worker._write(event)

        async with test_session_factory() as session:
            result = await session.exec(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.event_payload["event_id"].astext == str(event.event_id)
                )
            )
            record = result.one()
            assert record.event_source == AuditEventSource.BUSINESS_EVENT
            assert record.event_payload["event_action"] == "test_action"

    @pytest.mark.asyncio
    async def test_write_creates_outbox_record_with_business_event_source(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that write_to_outbox creates an outbox record with event_source=BUSINESS_EVENT."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )
        event = _make_event()

        # Use a session from the test fixture and call write_to_outbox
        async with test_session_factory() as session:
            # Convert AsyncSession to sync Session for the synchronous write_to_outbox
            worker.write_to_outbox(event, session.sync_session)
            await session.commit()

        async with test_session_factory() as session:
            result = await session.exec(
                select(AuditOutboxRecord).where(
                    AuditOutboxRecord.event_payload["event_id"].astext == str(event.event_id)
                )
            )
            record = result.one()
            assert record.event_source == AuditEventSource.BUSINESS_EVENT
            assert record.event_payload == event.model_dump(mode="json")

    @pytest.mark.asyncio
    async def test_write_handles_database_error(self) -> None:
        """Test that _write logs exceptions instead of raising."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit.side_effect = Exception("DB connection lost")
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=mock_session_factory,
            write_session_factory=mock_session_factory,
            coordinate=True,
        )
        event = _make_event()

        with patch("syntara.audit.outbox.worker.logger") as mock_logger:
            await worker._write(event)

            mock_logger.exception.assert_called_once_with(
                "audit_event_write_failed",
                event_id=str(event.event_id),
                actor_id=None,
                event_category="system_operation",
                event_action="test_action",
                source_component="test",
                exc_type="Exception",
            )

    @pytest.mark.asyncio
    async def test_write_converts_event_to_outbox_record(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that _write correctly stores AuditEvent fields in outbox record."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )
        event_id = uuid4()
        event = _make_event(event_id=event_id, event_action="specific_action")

        await worker._write(event)

        async with test_session_factory() as session:
            result = await session.exec(
                select(AuditOutboxRecord).where(AuditOutboxRecord.event_payload["event_id"].astext == str(event_id))
            )
            record = result.one()
            assert record.event_payload["event_action"] == "specific_action"
            assert record.event_payload["source_component"] == "test"


# ------------------------------------------------------------------ #
# Drain
# ------------------------------------------------------------------ #


class TestAuditEventWriterDrain:
    """Test AuditEventWriter.drain method."""

    @pytest.mark.asyncio
    async def test_drain_waits_for_pending_tasks(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that drain blocks until all in-flight tasks complete."""
        completed: list[object] = []

        async def slow_write(event: AuditEvent) -> None:
            await asyncio.sleep(0.05)
            completed.append(event.event_id)

        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )

        with patch.object(worker, "_write", side_effect=slow_write):
            for _ in range(3):
                worker.write_to_outbox(_make_event())

            # Tasks are still in-flight — not yet completed
            assert len(completed) == 0
            assert len(worker._pending) == 3

            await worker.drain()

        # All completed *because* drain waited
        assert len(completed) == 3

    @pytest.mark.asyncio
    async def test_drain_with_no_pending_tasks(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that drain completes immediately with no pending tasks."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )
        # Should not raise or hang
        await worker.drain()

    @pytest.mark.asyncio
    async def test_drain_handles_task_exceptions(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that drain handles exceptions in pending tasks gracefully."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )

        async def failing_write(event: AuditEvent) -> None:
            msg = "write failed"
            raise RuntimeError(msg)

        with patch.object(worker, "_write", side_effect=failing_write):
            worker.write_to_outbox(_make_event())

            # Should not raise despite task failure (return_exceptions=True)
            await worker.drain()

    @pytest.mark.asyncio
    async def test_drain_aborts_when_no_progress(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that drain breaks out of the loop when publish_outbox_events fails to reduce the pending count."""
        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=True,
        )

        with (
            patch.object(worker, "_get_pending_outbox_count", side_effect=[5, 5]),
            patch("syntara.audit.outbox.worker.publish_outbox_events", new_callable=AsyncMock) as mock_publish,
        ):
            await worker.drain()

        mock_publish.assert_called_once()


# ------------------------------------------------------------------ #
# Retry Logic
# ------------------------------------------------------------------ #


class TestAuditEventWriterRetry:
    """Test AuditEventWriter retry logic for transient database errors."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_transient_error(self) -> None:
        """Test that write retries and succeeds after transient OperationalError."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        # Fail twice with OperationalError, then succeed
        call_count = 0

        async def commit_side_effect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                msg = "connection lost"
                raise OperationalError(msg, None, Exception(msg))

        mock_session.commit = AsyncMock(side_effect=commit_side_effect)
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=mock_session_factory,
            write_session_factory=mock_session_factory,
            coordinate=True,
        )
        event = _make_event()

        with patch("syntara.audit.outbox.worker.logger") as mock_logger:
            await worker._write(event)

            # Should log retry warnings
            assert mock_logger.warning.call_count == 2
            # First retry call
            mock_logger.warning.assert_any_call(
                "audit_event_write_retry",
                event_id=str(event.event_id),
                actor_id=None,
                event_category="system_operation",
                event_action="test_action",
                source_component="test",
                attempt=1,
                max_retries=3,
                delay=0.1,
                exc_type="OperationalError",
            )

        # Should have made 3 commit attempts (2 failures + 1 success)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_fails_after_max_attempts(self) -> None:
        """Test that write logs failure after exhausting all retries."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit.side_effect = DatabaseError("database unavailable", None, Exception("db error"))
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=mock_session_factory,
            write_session_factory=mock_session_factory,
            coordinate=True,
        )
        event = _make_event()

        with patch("syntara.audit.outbox.worker.logger") as mock_logger:
            await worker._write(event)

            # Should log 3 retry warnings (attempts 1, 2, 3)
            assert mock_logger.warning.call_count == 3

            # Should log final failure
            mock_logger.exception.assert_called_once_with(
                "audit_event_write_failed_all_retries",
                event_id=str(event.event_id),
                actor_id=None,
                event_category="system_operation",
                event_action="test_action",
                source_component="test",
                attempts=4,  # max_retries + 1
                exc_type="DatabaseError",
            )

    @pytest.mark.asyncio
    async def test_non_retryable_error_fails_immediately(self) -> None:
        """Test that non-retryable errors (IntegrityError) don't retry."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit.side_effect = IntegrityError("constraint violation", None, Exception("constraint"))
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        worker = AuditOutboxWorker(
            name="audit-outbox-worker",
            interval_seconds=1,
            session_factory=mock_session_factory,
            write_session_factory=mock_session_factory,
            coordinate=True,
        )
        event = _make_event()

        with patch("syntara.audit.outbox.worker.logger") as mock_logger:
            await worker._write(event)

            # Should not log retry warnings (no retries)
            assert mock_logger.warning.call_count == 0

            # Should log immediate failure
            mock_logger.exception.assert_called_once_with(
                "audit_event_write_failed",
                event_id=str(event.event_id),
                actor_id=None,
                event_category="system_operation",
                event_action="test_action",
                source_component="test",
                exc_type="IntegrityError",
            )

        # Should have only attempted once
        assert mock_session.commit.call_count == 1


# ------------------------------------------------------------------ #
# Semaphore
# ------------------------------------------------------------------ #


class TestAuditEventWriterSemaphore:
    """Test AuditEventWriter semaphore for limiting concurrent writes."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_writes(
        self, test_session_factory: async_sessionmaker[AsyncSession], override_settings
    ) -> None:
        """Test that semaphore limits concurrent database operations."""
        with override_settings(audit_writer_max_concurrent_writes=2):
            worker = AuditOutboxWorker(
                name="audit-outbox-worker",
                interval_seconds=1,
                session_factory=test_session_factory,
                write_session_factory=test_session_factory,
                coordinate=True,
            )

            # Track concurrent execution
            concurrent_count = 0
            max_concurrent = 0
            lock = asyncio.Lock()

            original_write = worker._write

            async def tracked_write(event: AuditEvent) -> None:
                nonlocal concurrent_count, max_concurrent
                async with lock:
                    concurrent_count += 1
                    max_concurrent = max(max_concurrent, concurrent_count)

                # Simulate slow write
                await asyncio.sleep(0.05)

                await original_write(event)

                async with lock:
                    concurrent_count -= 1

            with patch.object(worker, "_write", side_effect=tracked_write):
                # Enqueue more events than semaphore limit
                for _ in range(5):
                    worker.write_to_outbox(_make_event())

                await worker.drain()

            # Max concurrent should not exceed semaphore limit
            assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_custom_semaphore_limit(self, override_settings) -> None:
        """Test that settings control the semaphore limit."""
        with override_settings(audit_writer_max_concurrent_writes=50):
            worker = AuditOutboxWorker(
                name="audit-outbox-worker",
                interval_seconds=1,
                session_factory=MagicMock(),
                write_session_factory=MagicMock(),
                coordinate=True,
            )
            assert worker._semaphore._value == 50


# ------------------------------------------------------------------ #
# Malformed Record Handling
# ------------------------------------------------------------------ #


class TestMalformedRecordHandling:
    """Test handling of malformed audit outbox records."""

    @pytest.mark.asyncio
    async def test_business_event_malformed_record_dropped(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that malformed business events are logged and dropped during publish."""
        valid_event_1 = _make_event(event_action="action_1")
        valid_event_2 = _make_event(event_action="action_2")
        malformed_event_id = uuid4()

        valid_outbox_1 = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=valid_event_1.model_dump(mode="json"),
        )
        valid_outbox_2 = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=valid_event_2.model_dump(mode="json"),
        )
        malformed_outbox = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload={"event_id": str(malformed_event_id), "event_action": "malformed", "invalid": "data"},
        )

        async with test_session_factory() as session:
            session.add_all([valid_outbox_1, malformed_outbox, valid_outbox_2])
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.SUCCESS

        with (
            patch("syntara.audit.outbox.worker.logger") as mock_logger,
            patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build,
        ):
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "Dropped malformed AuditOutboxRecord record."
            assert "id" in call_args[1]

            # Verify only 2 events were built for OTEL (malformed one dropped)
            assert mock_build.call_count == 2
            emitted_event_ids = {call[0][0].event_id for call in mock_build.call_args_list}
            assert emitted_event_ids == {valid_event_1.event_id, valid_event_2.event_id}

        # Verify all outbox records were deleted (including malformed)
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_crud_event_malformed_record_dropped(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that malformed CRUD events are logged and dropped during publish."""
        valid_event_1 = _make_event(event_action="crud_action_1")
        valid_event_2 = _make_event(event_action="crud_action_2")
        malformed_event_id = uuid4()

        valid_outbox_1 = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload=valid_event_1.model_dump(mode="json"),
        )
        valid_outbox_2 = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload=valid_event_2.model_dump(mode="json"),
        )
        malformed_outbox = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload={"event_id": str(malformed_event_id), "event_category": "invalid", "missing_fields": True},
        )

        async with test_session_factory() as session:
            session.add_all([valid_outbox_1, malformed_outbox, valid_outbox_2])
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.SUCCESS

        with (
            patch("syntara.audit.outbox.worker.logger") as mock_logger,
            patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build,
        ):
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "Dropped malformed AuditOutboxRecord record."
            assert "id" in call_args[1]

            # Verify only 2 events were built for OTEL (malformed one dropped)
            assert mock_build.call_count == 2

            # Verify the built events are the valid ones (malformed one should not be present)
            emitted_event_ids = {call[0][0].event_id for call in mock_build.call_args_list}
            assert emitted_event_ids == {valid_event_1.event_id, valid_event_2.event_id}
            assert malformed_event_id not in emitted_event_ids

        # Verify all outbox records were deleted (including malformed)
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 0


# ------------------------------------------------------------------ #
# OTEL Export Failure Handling
# ------------------------------------------------------------------ #


class TestOtelExportFailureRetainsRecords:
    """Test that outbox records are NOT deleted when OTEL export fails."""

    @pytest.mark.asyncio
    async def test_records_retained_on_export_failure(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that outbox records are NOT deleted when exporter.export() returns FAILURE."""
        event = _make_event(event_action="important_audit_action")
        outbox_record = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add(outbox_record)
            await session.commit()

        # Simulate OTEL export failure
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.FAILURE

        with (
            patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build,
            patch("syntara.audit.outbox.worker.logger") as mock_logger,
        ):
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

            # Verify warning was logged about failed export
            mock_logger.warning.assert_any_call(
                "OTEL export failed. %s",
                _OTEL_DISPATCH_RETRY_MESSAGE,
                batch_size=1,
                max_dispatch_attempts=5,
            )

        # Records must still be in the outbox for retry
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 1, "Outbox record should be retained on export failure"

            # Clean up retained records to avoid polluting subsequent tests
            for record in remaining:
                await session.delete(record)
            await session.commit()

    @pytest.mark.asyncio
    async def test_records_deleted_on_export_success(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that outbox records ARE deleted when exporter.export() returns SUCCESS."""
        event = _make_event(event_action="successful_audit_action")
        outbox_record = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add(outbox_record)
            await session.commit()

        # Simulate OTEL export success
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.SUCCESS

        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

        # Records should be deleted after successful export
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 0, "Outbox records should be deleted after successful export"

    @pytest.mark.asyncio
    async def test_records_deleted_when_otel_disabled(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that outbox records are deleted when OTEL is disabled (no destination)."""
        event = _make_event(event_action="otel_disabled_action")
        outbox_record = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add(outbox_record)
            await session.commit()

        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory)

        # Records should be deleted — no OTEL destination means no point retaining
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 0, "Outbox records should be deleted when OTEL is disabled"

    @pytest.mark.asyncio
    async def test_multiple_records_retained_on_batch_export_failure(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that all records in a batch are retained when export fails."""
        events = [_make_event(event_action=f"batch_action_{i}") for i in range(3)]
        outbox_records = [
            AuditOutboxRecord(
                event_source=AuditEventSource.BUSINESS_EVENT,
                event_payload=event.model_dump(mode="json"),
            )
            for event in events
        ]

        async with test_session_factory() as session:
            session.add_all(outbox_records)
            await session.commit()

        # Simulate batch export failure
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.FAILURE

        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

        # All 3 records must still be in the outbox
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 3, "All outbox records should be retained on batch export failure"

            # Clean up retained records to avoid polluting subsequent tests
            for record in remaining:
                await session.delete(record)
            await session.commit()


# ------------------------------------------------------------------ #
# OTEL Export Dispatch Attempts
# ------------------------------------------------------------------ #


class TestOtelExportDispatchAttempts:
    """Test that failed exports increment dispatch_attempts and drop records that exceed the threshold."""

    @pytest.mark.asyncio
    async def test_export_failure_increments_dispatch_attempts(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Each export failure increments dispatch_attempts on retained outbox records."""
        event = _make_event(event_action="retry_action")
        outbox_record = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add(outbox_record)
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.FAILURE

        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            # First failure: 0 -> 1
            await publish_outbox_events(test_session_factory, mock_exporter, max_dispatch_attempts=5)

        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 1
            assert remaining[0].dispatch_attempts == 1

        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            # Second failure: 1 -> 2
            await publish_outbox_events(test_session_factory, mock_exporter, max_dispatch_attempts=5)

        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 1
            assert remaining[0].dispatch_attempts == 2

            # Clean up
            for record in remaining:
                await session.delete(record)
            await session.commit()

    @pytest.mark.asyncio
    async def test_record_deleted_when_dispatch_attempts_exceeds_threshold(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Records exceeding max_dispatch_attempts are logged as CRITICAL and deleted."""
        event = _make_event(event_action="doomed_action")
        outbox_record = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event.model_dump(mode="json"),
            dispatch_attempts=2,
        )

        async with test_session_factory() as session:
            session.add(outbox_record)
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.FAILURE

        with (
            patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build,
            patch("syntara.audit.outbox.worker.logger") as mock_logger,
        ):
            mock_build.return_value = MagicMock()

            # max_dispatch_attempts=2, current is 2, will increment to 3 which exceeds threshold
            await publish_outbox_events(test_session_factory, mock_exporter, max_dispatch_attempts=2)

            mock_logger.critical.assert_called_once()
            call_args = mock_logger.critical.call_args
            assert call_args[0][0] == "Audit event permanently failed OTEL export, deleting from outbox"
            assert call_args[1]["event_id"] == str(event.event_id)
            assert call_args[1]["dispatch_attempts"] == 3

        # Record should be deleted
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 0, "Record should be deleted after exceeding max_dispatch_attempts"


# ------------------------------------------------------------------ #
# OTEL Event Source Discriminator
# ------------------------------------------------------------------ #


class TestOtelEventSourceDiscriminator:
    """Test that OTEL events include the audit.event_source discriminator field."""

    @pytest.mark.asyncio
    async def test_business_event_includes_event_source_discriminator(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that business events emitted to OTEL include audit.event_source=business."""
        event_1 = _make_event(event_action="business_action_1")
        event_2 = _make_event(event_action="business_action_2")

        outbox_1 = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event_1.model_dump(mode="json"),
        )
        outbox_2 = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event_2.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add_all([outbox_1, outbox_2])
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.SUCCESS

        # Mock _build_otel_log_record to capture calls and verify event_source
        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

            # Verify each call includes event_source=BUSINESS_EVENT
            assert mock_build.call_count == 2
            for call in mock_build.call_args_list:
                args, kwargs = call
                assert isinstance(args[0], AuditEvent)
                event_source = args[2] if len(args) > 2 else kwargs.get("event_source")
                assert event_source == AuditEventSource.BUSINESS_EVENT

    @pytest.mark.asyncio
    async def test_crud_event_includes_event_source_discriminator(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that CRUD events emitted to OTEL include audit.event_source=crud."""
        event_1 = _make_event(event_action="crud_action_1")
        event_2 = _make_event(event_action="crud_action_2")

        outbox_1 = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload=event_1.model_dump(mode="json"),
        )
        outbox_2 = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload=event_2.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add_all([outbox_1, outbox_2])
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.SUCCESS

        # Mock _build_otel_log_record to capture calls and verify event_source
        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

            # Verify each call includes event_source=CRUD_EVENT
            assert mock_build.call_count == 2
            for call in mock_build.call_args_list:
                args, kwargs = call
                assert isinstance(args[0], AuditEvent)
                event_source = args[2] if len(args) > 2 else kwargs.get("event_source")
                assert event_source == AuditEventSource.CRUD_EVENT

    @pytest.mark.asyncio
    async def test_mixed_events_have_correct_discriminators(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Test that mixed business and CRUD events have correct event_source values."""
        business_event = _make_event(event_action="business_action")
        crud_event = _make_event(event_action="crud_action")

        business_outbox = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=business_event.model_dump(mode="json"),
        )
        crud_outbox = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload=crud_event.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add_all([business_outbox, crud_outbox])
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.SUCCESS

        # Mock _build_otel_log_record to capture calls and verify event_source
        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()

            await publish_outbox_events(test_session_factory, mock_exporter)

            # Verify we have one of each type
            assert mock_build.call_count == 2
            event_sources = []
            for call in mock_build.call_args_list:
                args, kwargs = call
                event_sources.append(args[2] if len(args) > 2 else kwargs.get("event_source"))

            assert AuditEventSource.BUSINESS_EVENT in event_sources
            assert AuditEventSource.CRUD_EVENT in event_sources
            assert len(event_sources) == 2


# ------------------------------------------------------------------ #
# CRUD sanitize path (AAP-83644)
# ------------------------------------------------------------------ #


class TestCrudOutboxSanitization:
    """CRUD outbox records are sanitized before OTEL emit (trigger path is unsanitized)."""

    def test_crud_outbox_redacts_nested_password_hash_changes(self) -> None:
        """AAP-83644: worker sanitize redacts password_hash old/new on real CRUD shape."""
        event = _make_event(
            event_action="user_update",
            source_component="database.trigger",
            structured_data=AuditContextData(
                data_type="crud_operation",
                operation="update",
                model_name="User",
                changes={
                    "password_hash": {
                        "old": "$argon2id$v=19$m=65536,t=3,p=4$oldhash",
                        "new": "$argon2id$v=19$m=65536,t=3,p=4$newhash",
                    },
                    "username": "alice",
                },
            ),
        )
        record = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()
            _handle_crud_audit_records([record])

            mock_build.assert_called_once()
            emitted_event = mock_build.call_args[0][0]
            assert mock_build.call_args.kwargs["event_source"] == AuditEventSource.CRUD_EVENT

            changes = emitted_event.structured_data.changes
            assert changes["password_hash"] == {"old": REDACTED, "new": REDACTED}
            assert changes["username"] == "alice"
            assert "$argon2id$" not in str(changes)

    def test_crud_outbox_redacts_nested_secret_id_changes(self) -> None:
        """AAP-83644: same worker path for identityprovider.secret_id diffs."""
        event = _make_event(
            event_action="identityprovider_update",
            source_component="database.trigger",
            structured_data=AuditContextData(
                data_type="crud_operation",
                operation="update",
                model_name="IdentityProvider",
                changes={
                    "secret_id": {
                        "old": "old-secret-uuid",
                        "new": "new-secret-uuid",
                    }
                },
            ),
        )
        record = AuditOutboxRecord(
            event_source=AuditEventSource.CRUD_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        with patch("syntara.audit.outbox.worker._build_otel_log_record") as mock_build:
            mock_build.return_value = MagicMock()
            _handle_crud_audit_records([record])

            changes = mock_build.call_args[0][0].structured_data.changes
            assert changes["secret_id"] == {"old": REDACTED, "new": REDACTED}


# ------------------------------------------------------------------ #
# Audit Event stdout Logging
# ------------------------------------------------------------------ #


class TestAuditEventStdoutLogging:
    """Test that audit events are logged to stdout via the audit logger."""

    @pytest.mark.asyncio
    async def test_audit_events_logged_to_stdout(self, test_session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Audit events are logged to the audit logger with correct body and attributes."""
        event = _make_event(event_action="credential_create")
        outbox_record = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add(outbox_record)
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = LogRecordExportResult.SUCCESS

        with patch("syntara.audit.outbox.worker.audit_logger") as mock_audit_logger:
            await publish_outbox_events(test_session_factory, mock_exporter)

            mock_audit_logger.info.assert_called_once()
            call_args, call_kwargs = mock_audit_logger.info.call_args

            # Body includes event_id so Loki does not collapse co-timestamped siblings
            assert call_args[0] == f"audit_event:{event.event_id}"

            # Attributes contain the serialised event fields
            assert call_kwargs["event_action"] == "credential_create"
            assert call_kwargs["event_category"] == "system_operation"
            assert call_kwargs["source_component"] == "test"
            assert call_kwargs["audit.event_source"] == "business_event"
            assert "event_id" in call_kwargs


# ------------------------------------------------------------------ #
# OTEL Export Exception Handling
# ------------------------------------------------------------------ #


class TestOtelExportExceptionRetainsRecords:
    """Test that outbox records are retained when exporter.export() raises."""

    @pytest.mark.asyncio
    async def test_records_retained_on_export_exception(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Outbox records are NOT deleted when exporter.export() raises an exception."""
        event = _make_event(event_action="exception_test_action")
        outbox_record = AuditOutboxRecord(
            event_source=AuditEventSource.BUSINESS_EVENT,
            event_payload=event.model_dump(mode="json"),
        )

        async with test_session_factory() as session:
            session.add(outbox_record)
            await session.commit()

        mock_exporter = MagicMock()
        mock_exporter.export.side_effect = ConnectionError("network unreachable")

        with patch("syntara.audit.outbox.worker.logger") as mock_logger:
            await publish_outbox_events(test_session_factory, mock_exporter)

            mock_logger.exception.assert_any_call(
                "OTEL export raised exception. %s",
                _OTEL_DISPATCH_RETRY_MESSAGE,
                batch_size=1,
                max_dispatch_attempts=5,
            )

        # Records must still be in the outbox for retry
        async with test_session_factory() as session:
            result = await session.exec(select(AuditOutboxRecord))
            remaining = result.all()
            assert len(remaining) == 1, "Outbox record should be retained on export exception"

            for record in remaining:
                await session.delete(record)
            await session.commit()


# ------------------------------------------------------------------ #
# OTEL Log Entry Serialization
# ------------------------------------------------------------------ #


class TestBuildOtelLogRecordSerialization:
    """Test _build_otel_log_record produces OTLP-safe output.

    Regression: asyncpg.pgproto.pgproto.UUID in structured_data extra fields
    caused ``Invalid type <class 'asyncpg.pgproto.pgproto.UUID'>`` errors in
    the OTLP protobuf encoder, which only accepts JSON-native Python types.
    """

    def test_output_is_json_serializable(self, override_settings) -> None:
        """All attribute values in the OTEL log record must be JSON-native types."""
        event = _make_event(
            actor_id=uuid4(),
            workflow_id=uuid4(),
            execution_id=uuid4(),
            structured_data=AuditContextData(
                data_type="crud_operation",
                resource_id=str(uuid4()),
            ),
        )

        with override_settings(otel_service_name="nexus-test"):
            record = _build_otel_log_record(event, datetime.now(UTC), AuditEventSource.BUSINESS_EVENT)

        attrs = record.log_record.attributes
        assert attrs is not None
        assert attrs["audit.event_source"] == "business_event"
        assert record.log_record.body == f"audit_event:{event.event_id}"

        # Must not raise TypeError — no UUID objects, datetimes, etc.
        json.dumps(dict(attrs))

    def test_sibling_events_get_distinct_bodies(self, override_settings) -> None:
        """Same timestamp must not produce identical export bodies (log-store dedup)."""
        shared_ts = datetime.now(UTC)
        event_a = _make_event(event_action="project_create")
        event_b = _make_event(event_action="roleassignment_create")

        with override_settings(otel_service_name="nexus-test"):
            record_a = _build_otel_log_record(event_a, shared_ts, AuditEventSource.CRUD_EVENT)
            record_b = _build_otel_log_record(event_b, shared_ts, AuditEventSource.CRUD_EVENT)

        assert record_a.log_record.timestamp == record_b.log_record.timestamp
        assert record_a.log_record.body != record_b.log_record.body
        assert record_a.log_record.body == f"audit_event:{event_a.event_id}"
        assert record_b.log_record.body == f"audit_event:{event_b.event_id}"

    def test_uuid_subclass_in_extra_fields_coerced(self, override_settings) -> None:
        """UUID subclasses (e.g. asyncpg UUID) in extra fields become strings."""

        class ForeignUUID(UUID):
            """Simulates asyncpg.pgproto.pgproto.UUID."""

        event = _make_event(
            event_id=ForeignUUID("34929735-b33e-491d-b444-757da31dc6bf"),
            structured_data=AuditContextData(
                data_type="crud_operation",
                resource_id=ForeignUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            ),
        )

        with override_settings(otel_service_name="nexus-test"):
            record = _build_otel_log_record(event, datetime.now(UTC), AuditEventSource.CRUD_EVENT)

        attrs = record.log_record.attributes
        assert attrs is not None
        assert isinstance(attrs["event_id"], str)
        structured_data = attrs["structured_data"]
        assert isinstance(structured_data, dict)
        assert isinstance(structured_data["resource_id"], str)

        # Must not raise TypeError — no UUID subclass objects
        json.dumps(dict(attrs))
