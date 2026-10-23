# Kafka record runner recovery

The single-subscription runner uses explicit resolution-only Kafka commits.
Validation-only inspection never grants workflow admission or commit permission.
It may read back an already delivered, uninspected offset window while a recovery
fence closes normal admission. Kafka ownership and the assignment epoch are still
required for every seek, fetch and commit. This is not a general replay interface.

## Content inspection evidence

Before decoding, the processing service commits an ordinary delivery row with
`last_error_code=content_inspection_pending` and a finite, token-fenced inspection
claim. This records unknown content status without storing the source body.
The marker remains protective after lease expiry, cancellation and restart.

Successful validation-only inspection replaces the marker with
`content_validated`. Normal processing keeps the marker until durable Execution
preparation is frozen. A permanent decoding/schema error replaces it with its
safe error code and remains unresolved until the required activity log exists.
Failed inspection finalization retains the pending marker. Dependency, permission,
quota and capacity failures do not become permanent content decisions.

Gap reconciliation, boundary confirmation and retention verification all respect
pending inspection evidence. Missing source records or unavailable evidence must
leave the gate closed. Shutdown and revocation use their existing drain deadline;
they cannot turn unresolved inspection into acknowledgement permission.

The implementation reuses the existing delivery schema and requires no DDL
migration. Unit tests use isolated storage and transport adapters; they do not
establish live database durability, broker connectivity or cross-process behavior.

## Safe code rollback

Do not roll recovery/cleanup code back to a version that ignores
`content_inspection_pending` while such rows remain. Stop new intake and use the
current inspection and recovery services to reconcile every pending inspection
first. Preserve permanent error rows and frozen/ambiguous Execution evidence.

If a pending inspection cannot be completed, retain the marker and keep the
compatible recovery/cleanup code deployed. Lease expiry, row deletion, clearing
the marker, or advancing Kafka offsets are not safe substitutes for evidence.

Queue, concurrency and drain defaults are configured through the documented
`APP_EVENT_*` settings in `.env.example`. Changes apply on runner restart.
