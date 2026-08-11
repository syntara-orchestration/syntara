"""Audit event outbox for guaranteed delivery.

The outbox pattern ensures audit events are never lost by writing them to the
main database within the same transaction as business data changes, then having
a background worker publish them to the audit database asynchronously.

Architecture:
- AuditOutboxRecord: Temporary table in main database (transactionally consistent)
- OutboxWorker: Background worker that publishes unpublished records
- Session listener: Writes to outbox instead of dispatching directly

This guarantees at-least-once delivery of audit events even if the process
crashes between business commit and audit write.
"""
