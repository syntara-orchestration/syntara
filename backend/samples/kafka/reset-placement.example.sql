-- Manual operational-state example; never part of setup or compose startup.
-- Close admission and stop all consumers, recovery loops and cache readers/writers first.
-- Coordinate the external cache epoch separately before restored state is reactivated.
-- Supply the existing stable Installation.id with psql --set=deployment_id=... .
-- Delivery tokens, source/group boundaries and Execution evidence must remain intact.
BEGIN;

UPDATE event_subscriptions AS subscription
SET assigned_worker_id = NULL,
    assignment_lease_until = NULL
WHERE EXISTS (
    SELECT 1
    FROM event_subscription_sources AS source
    WHERE source.subscription_id = subscription.id
      AND source.generation = subscription.active_source_generation
      AND source.deployment_id = :'deployment_id'
);

DELETE FROM event_consumer_workers
WHERE deployment_id = :'deployment_id';

COMMIT;
