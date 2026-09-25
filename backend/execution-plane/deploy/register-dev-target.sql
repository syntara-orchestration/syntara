-- Run after the execution_plane Alembic migrations. The bearer token is not
-- persisted: credential_ref points at the short-lived token mounted by compose.
-- Invoke psql with: -v endpoint="$(oc whoami --show-server)"
INSERT INTO execution_plane.execution_targets (
    id,
    name,
    backend_type,
    endpoint,
    namespace,
    credential_ref,
    status,
    enabled,
    labels,
    created_at
)
VALUES (
    '18030000-0000-4000-8000-000000000001',
    'dev-openshift-cluster',
    'vanilla_k8s',
    :'endpoint',
    'ep-dev-workers',
    '{"type":"file","path":"/run/secrets/execution-plane/openshift-token","verify_ssl":true}'::jsonb,
    'active',
    true,
    '{"environment":"development","execution-mode":"cold-start","platform":"openshift"}'::jsonb,
    CURRENT_TIMESTAMP
)
ON CONFLICT (name) DO UPDATE SET
    backend_type = EXCLUDED.backend_type,
    endpoint = EXCLUDED.endpoint,
    namespace = EXCLUDED.namespace,
    credential_ref = EXCLUDED.credential_ref,
    status = EXCLUDED.status,
    enabled = EXCLUDED.enabled,
    labels = EXCLUDED.labels;
