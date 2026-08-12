-- Baseline schema. Applied by the sibling .py revision.

SET check_function_bodies = false;

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';

CREATE TYPE public.activitystatus AS ENUM (
    'pending',
    'running',
    'waiting',
    'completed',
    'failed',
    'retrying',
    'skipped',
    'cancelled'
);

CREATE TYPE public.approvalrequeststatus AS ENUM (
    'pending',
    'approved',
    'rejected',
    'expired',
    'cancelled'
);

CREATE TYPE public.auditeventsource AS ENUM (
    'business_event',
    'crud_event'
);

CREATE TYPE public.countertype AS ENUM (
    'PROVIDER',
    'TOOL',
    'USER',
    'PROVIDER_USER',
    'TOOL_USER'
);

CREATE TYPE public.executionmode AS ENUM (
    'standard',
    'test',
    'debug'
);

CREATE TYPE public.filestatus AS ENUM (
    'PENDING_CONVERSION',
    'CONVERTING',
    'CONVERTED',
    'CONVERSION_FAILED'
);

CREATE TYPE public.integration_refresh_status AS ENUM (
    'refreshing',
    'available',
    'warning',
    'error'
);

CREATE TYPE public.integration_scope AS ENUM (
    'global',
    'project'
);

CREATE TYPE public.integration_status AS ENUM (
    'validating',
    'available',
    'error',
    'unknown'
);

CREATE TYPE public.integration_type AS ENUM (
    'mcp_server',
    'llm_provider',
    'ansible_automation_platform'
);

CREATE TYPE public.invocationstatus AS ENUM (
    'created',
    'running',
    'paused',
    'cancelled',
    'completed',
    'failed'
);

CREATE TYPE public.nodetype AS ENUM (
    'manual_trigger',
    'scheduled_trigger',
    'webhook_trigger',
    'eda_trigger',
    'condition',
    'converge',
    'loop',
    'switch',
    'wait',
    'aap_job_template',
    'aap_workflow_job_template',
    'agentic',
    'approval',
    'http_request',
    'internal_activity',
    'script'
);

CREATE TYPE public.publishaction AS ENUM (
    'published',
    'unpublished'
);

CREATE TYPE public.settingvaluetype AS ENUM (
    'string',
    'integer',
    'float',
    'boolean',
    'json'
);

CREATE TYPE public.targettype AS ENUM (
    'PROVIDER',
    'TOOL',
    'USER'
);

CREATE TYPE public.tool_parameter_type AS ENUM (
    'string',
    'number',
    'boolean',
    'object',
    'array'
);

CREATE TYPE public.tool_status AS ENUM (
    'available',
    'missing',
    'error'
);

CREATE TYPE public.toolexecutionstatus AS ENUM (
    'RUNNING',
    'SUCCESS',
    'ERROR',
    'TIMEOUT'
);

CREATE TYPE public.userrole AS ENUM (
    'creator',
    'approver',
    'administrator',
    'viewer'
);

CREATE TYPE public.windowduration AS ENUM (
    'HOUR',
    'DAY',
    'MONTH'
);

CREATE TYPE public.workflowexecutionstatus AS ENUM (
    'pending',
    'running',
    'paused',
    'completed',
    'completed_with_errors',
    'failed',
    'cancelled'
);

CREATE FUNCTION public._build_changes(p_old_row jsonb, p_new_row jsonb, p_audit_level text, p_auditable_fields text[]) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_changes jsonb := '{}'::jsonb;
            v_field text;
            v_old_val jsonb;
            v_new_val jsonb;
            v_fields_to_check text[];
        BEGIN
            IF upper(coalesce(p_audit_level, 'META')) = 'FULL' THEN
                v_fields_to_check := ARRAY(
                    SELECT DISTINCT key
                    FROM (
                        SELECT jsonb_object_keys(p_old_row) AS key
                        UNION
                        SELECT jsonb_object_keys(p_new_row) AS key
                    ) s
                );
            ELSE
                v_fields_to_check := coalesce(p_auditable_fields, ARRAY[]::text[]);
            END IF;

            FOREACH v_field IN ARRAY v_fields_to_check LOOP
                v_old_val := p_old_row -> v_field;
                v_new_val := p_new_row -> v_field;

                IF v_old_val IS DISTINCT FROM v_new_val THEN
                    v_changes := v_changes || jsonb_build_object(
                        v_field,
                        jsonb_build_object(
                            'old', v_old_val,
                            'new', v_new_val
                        )
                    );
                END IF;
            END LOOP;

            RETURN v_changes;
        END;
        $$;

CREATE FUNCTION public._build_resource_snapshot(p_row jsonb, p_audit_level text, p_auditable_fields text[]) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_snapshot jsonb := '{}'::jsonb;
            v_field text;
        BEGIN
            IF upper(coalesce(p_audit_level, 'META')) = 'FULL' THEN
                RETURN p_row;
            END IF;

            IF p_auditable_fields IS NULL THEN
                RETURN '{}'::jsonb;
            END IF;

            FOREACH v_field IN ARRAY p_auditable_fields LOOP
                IF p_row ? v_field THEN
                    v_snapshot := v_snapshot || jsonb_build_object(
                        v_field,
                        p_row -> v_field
                    );
                END IF;
            END LOOP;

            RETURN v_snapshot;
        END;
        $$;

CREATE FUNCTION public.audit_crud_operation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_actor_id uuid;
            v_actor_username text;
            v_actor_type text;
            v_workflow_id uuid;
            v_execution_id uuid;
            v_activity_id text;

            v_audit_level text;
            v_auditable_fields text[];

            v_operation text;
            v_model_name text;
            v_resource_id uuid;
            v_resource_urn text;
            v_resource_name text;

            v_resource_data jsonb;
            v_changes jsonb;
            v_audit_event jsonb;

            v_old_json jsonb;
            v_new_json jsonb;

            v_event_verb text;
        BEGIN
            IF TG_TABLE_NAME = 'audit_outbox' THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                ELSE
                    RETURN NEW;
                END IF;
            END IF;

            BEGIN
                BEGIN
                    v_actor_id := nullif(current_setting('app.actor_id', true), '')::uuid;
                EXCEPTION WHEN invalid_text_representation THEN
                    v_actor_id := NULL;
                END;

                BEGIN
                    v_workflow_id := nullif(current_setting('app.workflow_id', true), '')::uuid;
                EXCEPTION WHEN invalid_text_representation THEN
                    v_workflow_id := NULL;
                END;

                BEGIN
                    v_execution_id := nullif(current_setting('app.execution_id', true), '')::uuid;
                EXCEPTION WHEN invalid_text_representation THEN
                    v_execution_id := NULL;
                END;

                v_actor_username := nullif(current_setting('app.actor_username', true), '');
                v_actor_type := nullif(current_setting('app.actor_type', true), '');
                v_activity_id := nullif(current_setting('app.activity_id', true), '');

                SELECT
                    model_name,
                    audit_level,
                    auditable_fields
                INTO
                    v_model_name,
                    v_audit_level,
                    v_auditable_fields
                FROM audit_table_metadata
                WHERE table_name = TG_TABLE_NAME;

                IF NOT FOUND THEN
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    ELSE
                        RETURN NEW;
                    END IF;
                END IF;

                IF TG_OP != 'DELETE' THEN
                    v_new_json := to_jsonb(NEW);
                END IF;

                IF TG_OP != 'INSERT' THEN
                    v_old_json := to_jsonb(OLD);
                END IF;

                IF TG_OP = 'INSERT' THEN
                    v_operation := 'create';
                    v_resource_id := (v_new_json ->> 'id')::uuid;

                ELSIF TG_OP = 'UPDATE' THEN
                    v_operation := 'update';
                    v_resource_id := coalesce(
                        (v_new_json ->> 'id')::uuid,
                        (v_old_json ->> 'id')::uuid
                    );

                ELSIF TG_OP = 'DELETE' THEN
                    v_operation := 'delete';
                    v_resource_id := (v_old_json ->> 'id')::uuid;
                END IF;

                v_resource_urn := format(
                    'urn:syntara:%s:%s',
                    coalesce(v_model_name, TG_TABLE_NAME),
                    coalesce(v_resource_id::text, 'unknown')
                );

                IF TG_OP = 'DELETE' THEN
                    v_resource_name := v_old_json ->> 'name';
                ELSE
                    v_resource_name := v_new_json ->> 'name';
                END IF;

                IF TG_OP = 'INSERT' THEN
                    v_resource_data := _build_resource_snapshot(
                        v_new_json,
                        v_audit_level,
                        v_auditable_fields
                    );

                    v_changes := NULL;

                ELSIF TG_OP = 'UPDATE' THEN
                    v_changes := _build_changes(
                        v_old_json,
                        v_new_json,
                        v_audit_level,
                        v_auditable_fields
                    );

                    v_resource_data := NULL;

                    IF v_changes = '{}'::jsonb THEN
                        RETURN NEW;
                    END IF;

                ELSIF TG_OP = 'DELETE' THEN
                    v_resource_data := _build_resource_snapshot(
                        v_old_json,
                        v_audit_level,
                        v_auditable_fields
                    );

                    v_changes := NULL;
                END IF;

                v_event_verb := CASE v_operation
                    WHEN 'create' THEN 'created'
                    WHEN 'update' THEN 'updated'
                    WHEN 'delete' THEN 'deleted'
                    ELSE v_operation
                END;

                v_audit_event := jsonb_build_object(
                    'event_id', uuid_generate_v7(),
                    'event_category', 'system_operation',
                    'event_severity', 'info',
                    'event_status', 'success',
                    'event_action', lower(v_model_name) || '_' || v_operation,
                    'actor_id', v_actor_id,
                    'actor_type', v_actor_type,
                    'actor_username', v_actor_username,
                    'source_component', 'database.trigger',
                    'resource_urn', v_resource_urn,
                    'resource_name', v_resource_name,
                    'workflow_id', v_workflow_id,
                    'activity_id', v_activity_id,
                    'execution_id', v_execution_id,
                    'event_message', v_model_name || ' ' || v_event_verb,
                    'structured_data', jsonb_build_object(
                        'data_type', 'crud_operation',
                        'operation', v_operation,
                        'model_name', v_model_name,
                        'resource_id', coalesce(v_resource_id::text, ''),
                        'changes', v_changes,
                        'resource_data', v_resource_data
                    )
                );

                INSERT INTO audit_outbox (
                    id,
                    created_at,
                    event_source,
                    event_payload
                ) VALUES (
                    uuid_generate_v7(),
                    now(),
                    'crud_event',
                    v_audit_event
                );

            EXCEPTION WHEN OTHERS THEN
                RAISE WARNING
                    'Audit trigger failed for %.% [%]: %',
                    TG_TABLE_SCHEMA,
                    TG_TABLE_NAME,
                    SQLSTATE,
                    SQLERRM;
            END;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            ELSE
                RETURN NEW;
            END IF;
        END;
        $$;

CREATE FUNCTION public.audit_trigger_disable(p_table_name text) RETURNS text
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_exists boolean;
        BEGIN
            SELECT EXISTS (
                SELECT 1
                FROM audit_table_metadata
                WHERE table_name = p_table_name
            ) INTO v_exists;

            IF NOT v_exists THEN
                RETURN 'error: table not in audit metadata';
            END IF;

            SELECT EXISTS (
                SELECT 1
                FROM pg_trigger t
                JOIN pg_class c ON t.tgrelid = c.oid
                WHERE c.relname = p_table_name
                  AND t.tgname = 'audit_trigger_' || p_table_name
                  AND NOT t.tgisinternal
            ) INTO v_exists;

            IF v_exists THEN
                EXECUTE format('DROP TRIGGER audit_trigger_%I ON %I', p_table_name, p_table_name);
                RETURN 'disabled';
            ELSE
                RETURN 'already disabled';
            END IF;
        END;
        $$;

CREATE FUNCTION public.audit_trigger_enable(p_table_name text) RETURNS text
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_exists boolean;
        BEGIN
            SELECT EXISTS (
                SELECT 1
                FROM audit_table_metadata
                WHERE table_name = p_table_name
            ) INTO v_exists;

            IF NOT v_exists THEN
                RETURN 'error: table not in audit metadata';
            END IF;

            SELECT EXISTS (
                SELECT 1
                FROM pg_trigger t
                JOIN pg_class c ON t.tgrelid = c.oid
                WHERE c.relname = p_table_name
                  AND t.tgname = 'audit_trigger_' || p_table_name
                  AND NOT t.tgisinternal
            ) INTO v_exists;

            IF NOT v_exists THEN
                EXECUTE format(
                    'CREATE TRIGGER audit_trigger_%I ' ||
                    'AFTER INSERT OR UPDATE OR DELETE ON %I ' ||
                    'FOR EACH ROW EXECUTE FUNCTION audit_crud_operation()',
                    p_table_name,
                    p_table_name
                );
                RETURN 'enabled';
            ELSE
                RETURN 'already enabled';
            END IF;
        END;
        $$;

CREATE FUNCTION public.audit_triggers_disable() RETURNS TABLE(table_name text, status text)
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_table_name text;
        BEGIN
            FOR v_table_name IN
                SELECT atm.table_name
                FROM audit_table_metadata atm
            LOOP
                IF EXISTS (
                    SELECT 1
                    FROM pg_trigger t
                    JOIN pg_class c ON t.tgrelid = c.oid
                    WHERE c.relname = v_table_name
                      AND t.tgname = 'audit_trigger_' || v_table_name
                      AND NOT t.tgisinternal
                ) THEN
                    EXECUTE format('DROP TRIGGER audit_trigger_%I ON %I', v_table_name, v_table_name);
                    table_name := v_table_name;
                    status := 'disabled';
                    RETURN NEXT;
                ELSE
                    table_name := v_table_name;
                    status := 'already disabled';
                    RETURN NEXT;
                END IF;
            END LOOP;
        END;
        $$;

CREATE FUNCTION public.audit_triggers_enable() RETURNS TABLE(table_name text, status text)
    LANGUAGE plpgsql
    AS $$
        DECLARE
            v_table_name text;
        BEGIN
            FOR v_table_name IN
                SELECT atm.table_name
                FROM audit_table_metadata atm
            LOOP
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_trigger t
                    JOIN pg_class c ON t.tgrelid = c.oid
                    WHERE c.relname = v_table_name
                      AND t.tgname = 'audit_trigger_' || v_table_name
                      AND NOT t.tgisinternal
                ) THEN
                    EXECUTE format(
                        'CREATE TRIGGER audit_trigger_%I ' ||
                        'AFTER INSERT OR UPDATE OR DELETE ON %I ' ||
                        'FOR EACH ROW EXECUTE FUNCTION audit_crud_operation()',
                        v_table_name,
                        v_table_name
                    );
                    table_name := v_table_name;
                    status := 'enabled';
                    RETURN NEXT;
                ELSE
                    table_name := v_table_name;
                    status := 'already enabled';
                    RETURN NEXT;
                END IF;
            END LOOP;
        END;
        $$;

CREATE FUNCTION public.audit_triggers_status() RETURNS TABLE(table_name text, model_name text, audit_level text, trigger_enabled boolean)
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RETURN QUERY
            SELECT
                atm.table_name,
                atm.model_name,
                atm.audit_level,
                EXISTS (
                    SELECT 1
                    FROM pg_trigger t
                    JOIN pg_class c ON t.tgrelid = c.oid
                    WHERE c.relname = atm.table_name
                      AND t.tgname = 'audit_trigger_' || atm.table_name
                      AND NOT t.tgisinternal
                ) AS trigger_enabled
            FROM audit_table_metadata atm
            ORDER BY atm.table_name;
        END;
        $$;

CREATE FUNCTION public.uuid_generate_v7() RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    ts_ms bigint;
    bytes bytea;
BEGIN
    ts_ms := extract(epoch FROM clock_timestamp()) * 1000;
    bytes := substring(int8send(ts_ms) FROM 3)   -- 6-byte ms timestamp
          || gen_random_bytes(10);                -- 10 random bytes
    bytes := set_byte(bytes, 6, (get_byte(bytes, 6) & x'0f'::int) | x'70'::int);
    bytes := set_byte(bytes, 8, (get_byte(bytes, 8) & x'3f'::int) | x'80'::int);
    RETURN encode(bytes, 'hex')::uuid;
END
$$;

CREATE TABLE public.activity_execution (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    execution_id uuid NOT NULL,
    activity_name character varying(255) NOT NULL,
    temporal_activity_id character varying(255) NOT NULL,
    status public.activitystatus NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    input_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_data jsonb,
    error_details text,
    retry_count integer DEFAULT 0 NOT NULL,
    iteration integer,
    node_type public.nodetype NOT NULL,
    CONSTRAINT ck_activity_execution_completed_after_started CHECK (((completed_at IS NULL) OR (started_at IS NULL) OR (completed_at >= started_at))),
    CONSTRAINT ck_activity_execution_iteration_non_negative CHECK (((iteration IS NULL) OR (iteration >= 0))),
    CONSTRAINT ck_activity_execution_retry_count_non_negative CHECK ((retry_count >= 0))
);

CREATE TABLE public.approval_approver_groups (
    approval_id uuid NOT NULL,
    group_id uuid NOT NULL
);

CREATE TABLE public.approval_approver_users (
    approval_id uuid NOT NULL,
    user_id uuid NOT NULL
);

CREATE TABLE public.approval_requests (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    name character varying(255) NOT NULL,
    execution_id uuid NOT NULL,
    approval_node_id character varying(255) NOT NULL,
    status public.approvalrequeststatus DEFAULT 'pending'::public.approvalrequeststatus NOT NULL,
    timeout_at timestamp with time zone,
    next_step_approved jsonb NOT NULL,
    next_step_rejected jsonb,
    workflow_context jsonb DEFAULT '{}'::jsonb NOT NULL,
    decided_by uuid,
    decided_at timestamp with time zone,
    decision_notes character varying(2000),
    project_id uuid NOT NULL
);

CREATE TABLE public.audit_outbox (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    event_source public.auditeventsource DEFAULT 'business_event'::public.auditeventsource NOT NULL,
    event_payload jsonb NOT NULL,
    dispatch_attempts integer DEFAULT 0 NOT NULL
);

CREATE TABLE public.audit_table_metadata (
    table_name character varying NOT NULL,
    model_name character varying NOT NULL,
    audit_level character varying NOT NULL,
    auditable_fields text[]
);

CREATE TABLE public.credential_types (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    inputs jsonb NOT NULL,
    injectors jsonb NOT NULL,
    managed boolean NOT NULL
);

CREATE TABLE public.credentials (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    name character varying(255) NOT NULL,
    description character varying(2000),
    credential_type_id uuid NOT NULL,
    secret_id uuid,
    enabled boolean NOT NULL,
    project_id uuid NOT NULL
);

CREATE TABLE public.encrypted_secrets (
    id uuid NOT NULL,
    secret_id uuid NOT NULL,
    encrypted_data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.executions (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by uuid,
    created_by uuid NOT NULL,
    updated_by uuid,
    workflow_id uuid NOT NULL,
    workflow_version_id uuid NOT NULL,
    temporal_workflow_id character varying(255) NOT NULL,
    status public.workflowexecutionstatus DEFAULT 'pending'::public.workflowexecutionstatus NOT NULL,
    completed_at timestamp with time zone,
    input_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_details text,
    last_processed_event_id bigint DEFAULT 0 NOT NULL,
    project_id uuid NOT NULL,
    trigger_node_id character varying(255),
    mode public.executionmode DEFAULT 'standard'::public.executionmode NOT NULL,
    execution_metadata jsonb,
    approval_pending boolean DEFAULT false NOT NULL,
    retried_from_execution_id uuid,
    trigger_type character varying(50),
    interface character varying(10),
    CONSTRAINT check_execution_completed_at_after_created_at CHECK (((completed_at IS NULL) OR (completed_at > created_at)))
);

CREATE TABLE public.file_metadata (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    filename character varying(255) NOT NULL,
    mime_type character varying(100) NOT NULL,
    size_bytes integer NOT NULL,
    file_path character varying(500) NOT NULL,
    converted_content_path character varying(500),
    status public.filestatus NOT NULL,
    conversion_error character varying,
    content_hash character varying(128),
    project_id uuid NOT NULL
);

CREATE TABLE public.global_revocation_timestamp (
    id integer NOT NULL,
    revoked_before timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_singleton boolean DEFAULT true NOT NULL,
    updated_by character varying,
    CONSTRAINT ck_global_revocation_singleton CHECK ((is_singleton = true))
);

CREATE SEQUENCE public.global_revocation_timestamp_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.global_revocation_timestamp_id_seq OWNED BY public.global_revocation_timestamp.id;

CREATE TABLE public.groups (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by uuid,
    name character varying(255) NOT NULL,
    description character varying(2000),
    created_by uuid,
    is_builtin boolean NOT NULL,
    source character varying(10) NOT NULL
);

CREATE TABLE public.identity_providers (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    name character varying(255) NOT NULL,
    description character varying(2000),
    enabled boolean NOT NULL,
    configuration jsonb NOT NULL,
    secret_id uuid
);

CREATE TABLE public.idp_group_mapping_entries (
    id uuid NOT NULL,
    identity_provider_id uuid NOT NULL,
    idp_group_value character varying NOT NULL,
    nexus_group_id uuid NOT NULL
);

CREATE TABLE public.installation (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    is_singleton boolean DEFAULT true NOT NULL,
    salt uuid NOT NULL,
    CONSTRAINT ck_installation_singleton CHECK ((is_singleton = true))
);

CREATE TABLE public.integration_project_assignments (
    id uuid NOT NULL,
    integration_id uuid NOT NULL,
    project_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.integrations (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    name character varying(255) NOT NULL,
    description character varying(2000),
    integration_type public.integration_type NOT NULL,
    enabled boolean NOT NULL,
    validation_status public.integration_status DEFAULT 'unknown'::public.integration_status NOT NULL,
    scope public.integration_scope NOT NULL,
    configuration jsonb NOT NULL,
    management_credential_id uuid,
    last_validated_at timestamp with time zone,
    validation_error text,
    refresh_status public.integration_refresh_status,
    last_refreshed_at timestamp with time zone,
    refresh_error text,
    last_successful_refresh_at timestamp with time zone
);

CREATE TABLE public.invocations (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    prompt text NOT NULL,
    session_id character varying(255) NOT NULL,
    status public.invocationstatus NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    context_data jsonb NOT NULL,
    result jsonb,
    checkpoint_data jsonb,
    error_message text,
    model_name character varying(255),
    project_id uuid NOT NULL,
    trace_events jsonb
);

CREATE TABLE public.llm_models (
    id uuid NOT NULL,
    integration_id uuid NOT NULL,
    model_id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(2000),
    enabled boolean NOT NULL,
    is_default boolean NOT NULL,
    last_refreshed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    profile jsonb
);

CREATE TABLE public.policies (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(2000),
    statements jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_builtin boolean NOT NULL,
    project_id uuid,
    scope character varying(20) NOT NULL
);

CREATE TABLE public.principals (
    id uuid NOT NULL,
    principal_type character varying(20) NOT NULL
);

CREATE TABLE public.projects (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by uuid,
    name character varying(255) NOT NULL,
    description character varying(2000),
    is_default boolean NOT NULL,
    is_builtin boolean DEFAULT false NOT NULL
);

CREATE TABLE public.rate_limits (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    target_type public.targettype NOT NULL,
    target_id character varying(255) NOT NULL,
    target_name character varying(255),
    requests_per_window integer NOT NULL,
    window_duration_seconds integer NOT NULL,
    burst_allowance integer NOT NULL,
    enabled boolean NOT NULL,
    current_usage integer NOT NULL,
    usage_reset_at timestamp with time zone
);

CREATE TABLE public.refresh_sessions (
    jti character varying(64) NOT NULL,
    user_id uuid NOT NULL,
    issued_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    device character varying(512),
    ip_address character varying(45),
    amr json,
    idp character varying(255),
    idp_id character varying(36),
    identity_id character varying(36),
    issuer character varying(2048),
    subject character varying(1024),
    id_token_hint character varying(4096),
    rp_logout_enabled boolean NOT NULL
);

CREATE TABLE public.role_assignments (
    principal_id uuid,
    role_name character varying(255) NOT NULL,
    project_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_builtin boolean NOT NULL,
    group_id uuid,
    CONSTRAINT ck_ra_principal_xor_group CHECK (((principal_id IS NOT NULL) <> (group_id IS NOT NULL)))
);

CREATE TABLE public.roles (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(2000),
    is_builtin boolean NOT NULL,
    project_id uuid,
    scope character varying(20) NOT NULL,
    policy_names jsonb DEFAULT '[]'::jsonb NOT NULL
);

CREATE TABLE public.runtime_settings (
    name character varying(255) NOT NULL,
    description character varying(2000),
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    key character varying(255) NOT NULL,
    value jsonb,
    default_value jsonb,
    value_type public.settingvaluetype NOT NULL,
    category character varying(255) NOT NULL,
    "group" character varying(255),
    requires_restart boolean NOT NULL,
    cache_ttl_seconds integer,
    validation_schema jsonb,
    version integer NOT NULL,
    helper_text character varying(2000),
    depends_on character varying(255),
    CONSTRAINT depends_on_format_check CHECK (((depends_on IS NULL) OR ((depends_on)::text ~ '^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$'::text)))
);

CREATE TABLE public.secrets (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.service_account_credentials (
    created_by uuid NOT NULL,
    updated_by uuid,
    service_account_id uuid NOT NULL,
    credential_type character varying(20) NOT NULL,
    identifier character varying(64) NOT NULL,
    hashed_secret text NOT NULL,
    old_hashed_secret text,
    old_secret_valid_until timestamp with time zone,
    grace_period_seconds integer NOT NULL,
    status character varying(10) NOT NULL,
    expires_at timestamp with time zone,
    last_used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_sa_credentials_grace_period_range CHECK (((grace_period_seconds >= 0) AND (grace_period_seconds <= 86400))),
    CONSTRAINT ck_sa_credentials_status_valid CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'disabled'::character varying])::text[]))),
    CONSTRAINT ck_sa_credentials_type_valid CHECK (((credential_type)::text = 'client_credentials'::text))
);

CREATE TABLE public.service_accounts (
    name character varying(255) NOT NULL,
    description character varying(2000),
    created_by uuid NOT NULL,
    updated_by uuid,
    status character varying(10) NOT NULL,
    project_id uuid NOT NULL,
    last_authenticated_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    token_version integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_service_accounts_status_valid CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'disabled'::character varying])::text[])))
);

CREATE TABLE public.setting_categories (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(2000),
    slug character varying(255) NOT NULL,
    display_order integer NOT NULL
);

CREATE TABLE public.token_usage_records (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    user_id uuid NOT NULL,
    token_count integer NOT NULL,
    request_timestamp timestamp with time zone,
    request_text_hash character varying(64),
    estimated_input_tokens integer,
    prompt_tokens integer,
    completion_tokens integer,
    invocation_id uuid,
    usage_details jsonb
);

CREATE TABLE public.tool_executions (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    tool_id uuid,
    user_id uuid NOT NULL,
    execution_start timestamp with time zone NOT NULL,
    execution_end timestamp with time zone,
    duration_ms integer,
    status public.toolexecutionstatus NOT NULL,
    input_parameters jsonb NOT NULL,
    output_data jsonb,
    error_message text,
    error_code character varying(100),
    integration_id uuid
);

CREATE TABLE public.tool_parameters (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    tool_id uuid NOT NULL,
    name character varying(100) NOT NULL,
    type public.tool_parameter_type NOT NULL,
    description text NOT NULL,
    required boolean NOT NULL,
    default_value jsonb,
    example_value jsonb
);

CREATE TABLE public.tools (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    name character varying(255) NOT NULL,
    description character varying(2000),
    namespaced_name character varying(200) NOT NULL,
    enabled boolean NOT NULL,
    status public.tool_status NOT NULL,
    last_executed_at timestamp with time zone,
    last_refreshed_at timestamp with time zone,
    refresh_error text,
    integration_id uuid NOT NULL
);

CREATE TABLE public.usage_counters (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    counter_type public.countertype NOT NULL,
    tool_id uuid,
    user_id uuid,
    time_window character varying(50) NOT NULL,
    window_duration public.windowduration NOT NULL,
    request_count integer NOT NULL,
    success_count integer NOT NULL,
    error_count integer NOT NULL,
    total_duration_ms integer NOT NULL,
    window_start timestamp with time zone NOT NULL,
    window_end timestamp with time zone NOT NULL,
    timeout_count integer DEFAULT 0 NOT NULL,
    integration_id uuid
);

CREATE TABLE public.user_groups (
    user_id uuid NOT NULL,
    group_id uuid NOT NULL
);

CREATE TABLE public.user_identities (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    identity_provider_id uuid NOT NULL,
    issuer character varying(2048) NOT NULL,
    subject character varying(1024) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    last_used_at timestamp with time zone
);

CREATE TABLE public.user_idp_groups (
    user_id uuid NOT NULL,
    identity_provider_id uuid NOT NULL,
    group_id uuid NOT NULL
);

CREATE TABLE public.user_token_configs (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    user_id uuid NOT NULL,
    token_limit integer NOT NULL,
    window_duration_seconds integer NOT NULL,
    model_name character varying DEFAULT 'gpt-4'::character varying NOT NULL
);

CREATE TABLE public.users (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by uuid,
    username character varying(255) NOT NULL,
    email character varying(255),
    last_login timestamp with time zone,
    preferences json NOT NULL,
    password_hash character varying(255),
    authz_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    is_builtin boolean DEFAULT false NOT NULL,
    token_version integer DEFAULT 0 NOT NULL,
    auth_type character varying(10) DEFAULT 'local'::character varying NOT NULL,
    first_name character varying(255) NOT NULL,
    last_name character varying(255),
    CONSTRAINT ck_users_auth_type_exclusivity CHECK ((((auth_type)::text = 'local'::text) OR (((auth_type)::text = 'federated'::text) AND (password_hash IS NULL))))
);

CREATE TABLE public.webhook_trigger_service_accounts (
    webhook_trigger_id uuid NOT NULL,
    service_account_id uuid NOT NULL
);

CREATE TABLE public.webhook_triggers (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    webhook_path character varying(128) NOT NULL,
    workflow_id uuid NOT NULL,
    trigger_node_id character varying(255) NOT NULL,
    input_schema jsonb,
    is_enabled boolean NOT NULL,
    trigger_type character varying(50) NOT NULL,
    CONSTRAINT ck_webhook_triggers_trigger_type_valid CHECK (((trigger_type)::text = ANY ((ARRAY['webhook_trigger'::character varying, 'eda_trigger'::character varying])::text[])))
);

CREATE TABLE public.workflow_publish_events (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    workflow_id uuid NOT NULL,
    version_id uuid NOT NULL,
    action public.publishaction NOT NULL,
    actor_id uuid
);

CREATE TABLE public.workflow_versions (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by uuid,
    created_by uuid NOT NULL,
    updated_by uuid,
    workflow_id uuid NOT NULL,
    version integer NOT NULL,
    schema_version character varying(50) NOT NULL,
    workflow_definition jsonb NOT NULL,
    change_description character varying(2000),
    name character varying(255)
);

CREATE TABLE public.workflows (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    labels jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid NOT NULL,
    updated_by uuid,
    deleted_at timestamp with time zone,
    deleted_by uuid,
    name character varying(255) NOT NULL,
    description character varying(2000),
    current_version integer NOT NULL,
    is_enabled boolean NOT NULL,
    project_id uuid NOT NULL,
    is_builtin boolean DEFAULT false NOT NULL,
    has_validation_issues boolean DEFAULT false NOT NULL,
    published_version_id uuid,
    CONSTRAINT ck_workflows_is_enabled_published_version_id CHECK (((published_version_id IS NULL) = (NOT is_enabled)))
);

ALTER TABLE ONLY public.global_revocation_timestamp ALTER COLUMN id SET DEFAULT nextval('public.global_revocation_timestamp_id_seq'::regclass);

ALTER TABLE ONLY public.activity_execution
    ADD CONSTRAINT activity_execution_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.approval_approver_groups
    ADD CONSTRAINT approval_approver_groups_pkey PRIMARY KEY (approval_id, group_id);

ALTER TABLE ONLY public.approval_approver_users
    ADD CONSTRAINT approval_approver_users_pkey PRIMARY KEY (approval_id, user_id);

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.audit_outbox
    ADD CONSTRAINT audit_outbox_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.audit_table_metadata
    ADD CONSTRAINT audit_table_metadata_pkey PRIMARY KEY (table_name);

ALTER TABLE ONLY public.credential_types
    ADD CONSTRAINT credential_types_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.encrypted_secrets
    ADD CONSTRAINT encrypted_secrets_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.encrypted_secrets
    ADD CONSTRAINT encrypted_secrets_secret_id_key UNIQUE (secret_id);

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT executions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.file_metadata
    ADD CONSTRAINT file_metadata_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.global_revocation_timestamp
    ADD CONSTRAINT global_revocation_timestamp_is_singleton_key UNIQUE (is_singleton);

ALTER TABLE ONLY public.global_revocation_timestamp
    ADD CONSTRAINT global_revocation_timestamp_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.identity_providers
    ADD CONSTRAINT identity_providers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.idp_group_mapping_entries
    ADD CONSTRAINT idp_group_mapping_entries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.installation
    ADD CONSTRAINT installation_is_singleton_key UNIQUE (is_singleton);

ALTER TABLE ONLY public.installation
    ADD CONSTRAINT installation_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.integration_project_assignments
    ADD CONSTRAINT integration_project_assignments_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.invocations
    ADD CONSTRAINT invocations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.identity_providers
    ADD CONSTRAINT ix_identity_providers_name_unique UNIQUE (name);

ALTER TABLE ONLY public.llm_models
    ADD CONSTRAINT llm_models_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.runtime_settings
    ADD CONSTRAINT pk_runtime_settings PRIMARY KEY (id);

ALTER TABLE ONLY public.setting_categories
    ADD CONSTRAINT pk_setting_categories PRIMARY KEY (id);

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.principals
    ADD CONSTRAINT principals_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.rate_limits
    ADD CONSTRAINT rate_limits_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.refresh_sessions
    ADD CONSTRAINT refresh_sessions_pkey PRIMARY KEY (jti);

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT role_assignments_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.secrets
    ADD CONSTRAINT secrets_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.service_account_credentials
    ADD CONSTRAINT service_account_credentials_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.service_accounts
    ADD CONSTRAINT service_accounts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.token_usage_records
    ADD CONSTRAINT token_usage_records_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.tool_executions
    ADD CONSTRAINT tool_executions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.tool_parameters
    ADD CONSTRAINT tool_parameters_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.tools
    ADD CONSTRAINT tools_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_execution
    ADD CONSTRAINT uix_execution_activity UNIQUE (execution_id, temporal_activity_id);

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT uix_execution_approval_node UNIQUE (execution_id, approval_node_id);

ALTER TABLE ONLY public.idp_group_mapping_entries
    ADD CONSTRAINT uq_idp_group_mapping_provider_value_group UNIQUE (identity_provider_id, idp_group_value, nexus_group_id);

ALTER TABLE ONLY public.integration_project_assignments
    ADD CONSTRAINT uq_integration_project UNIQUE (integration_id, project_id);

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT uq_integrations_name UNIQUE (name);

ALTER TABLE ONLY public.llm_models
    ADD CONSTRAINT uq_llm_models_integration_model UNIQUE (integration_id, model_id);

ALTER TABLE ONLY public.runtime_settings
    ADD CONSTRAINT uq_runtime_settings_key UNIQUE (key);

ALTER TABLE ONLY public.tools
    ADD CONSTRAINT uq_tools_namespaced_name UNIQUE (namespaced_name);

ALTER TABLE ONLY public.user_identities
    ADD CONSTRAINT uq_user_identities_issuer_subject UNIQUE (issuer, subject);

ALTER TABLE ONLY public.usage_counters
    ADD CONSTRAINT usage_counters_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_groups
    ADD CONSTRAINT user_groups_pkey PRIMARY KEY (user_id, group_id);

ALTER TABLE ONLY public.user_identities
    ADD CONSTRAINT user_identities_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_idp_groups
    ADD CONSTRAINT user_idp_groups_pkey PRIMARY KEY (user_id, identity_provider_id, group_id);

ALTER TABLE ONLY public.user_token_configs
    ADD CONSTRAINT user_token_configs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.webhook_trigger_service_accounts
    ADD CONSTRAINT webhook_trigger_service_accounts_pkey PRIMARY KEY (webhook_trigger_id, service_account_id);

ALTER TABLE ONLY public.webhook_triggers
    ADD CONSTRAINT webhook_triggers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.workflow_publish_events
    ADD CONSTRAINT workflow_publish_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.workflow_versions
    ADD CONSTRAINT workflow_versions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_pkey PRIMARY KEY (id);

CREATE INDEX ix_activity_execution_created_at ON public.activity_execution USING btree (created_at);

CREATE INDEX ix_activity_execution_execution_activity ON public.activity_execution USING btree (execution_id, activity_name);

CREATE INDEX ix_activity_execution_execution_id ON public.activity_execution USING btree (execution_id);

CREATE INDEX ix_activity_execution_execution_iteration ON public.activity_execution USING btree (execution_id, iteration);

CREATE INDEX ix_activity_execution_id ON public.activity_execution USING btree (id);

CREATE INDEX ix_activity_execution_node_type ON public.activity_execution USING btree (node_type);

CREATE INDEX ix_activity_execution_status ON public.activity_execution USING btree (status);

CREATE INDEX ix_activity_execution_updated_at ON public.activity_execution USING btree (updated_at);

CREATE INDEX ix_approval_requests_created_at ON public.approval_requests USING btree (created_at);

CREATE INDEX ix_approval_requests_execution_id ON public.approval_requests USING btree (execution_id);

CREATE INDEX ix_approval_requests_id ON public.approval_requests USING btree (id);

CREATE INDEX ix_approval_requests_name ON public.approval_requests USING btree (name);

CREATE INDEX ix_approval_requests_project_id ON public.approval_requests USING btree (project_id);

CREATE INDEX ix_approval_requests_status ON public.approval_requests USING btree (status);

CREATE INDEX ix_approval_requests_timeout_at ON public.approval_requests USING btree (timeout_at);

CREATE INDEX ix_approval_requests_updated_at ON public.approval_requests USING btree (updated_at);

CREATE INDEX ix_audit_outbox_created_at ON public.audit_outbox USING btree (created_at);

CREATE INDEX ix_credential_types_created_at ON public.credential_types USING btree (created_at);

CREATE INDEX ix_credential_types_id ON public.credential_types USING btree (id);

CREATE UNIQUE INDEX ix_credential_types_name ON public.credential_types USING btree (name);

CREATE INDEX ix_credential_types_updated_at ON public.credential_types USING btree (updated_at);

CREATE INDEX ix_credentials_created_at ON public.credentials USING btree (created_at);

CREATE INDEX ix_credentials_created_at_id ON public.credentials USING btree (created_at, id);

CREATE INDEX ix_credentials_created_by ON public.credentials USING btree (created_by);

CREATE INDEX ix_credentials_credential_type_id ON public.credentials USING btree (credential_type_id);

CREATE INDEX ix_credentials_id ON public.credentials USING btree (id);

CREATE INDEX ix_credentials_name ON public.credentials USING btree (name);

CREATE UNIQUE INDEX ix_credentials_name_project_unique ON public.credentials USING btree (name, project_id);

CREATE INDEX ix_credentials_project_id ON public.credentials USING btree (project_id);

CREATE INDEX ix_credentials_secret_id ON public.credentials USING btree (secret_id);

CREATE INDEX ix_credentials_updated_at ON public.credentials USING btree (updated_at);

CREATE INDEX ix_credentials_updated_by ON public.credentials USING btree (updated_by);

CREATE INDEX ix_encrypted_secrets_secret_id ON public.encrypted_secrets USING btree (secret_id);

CREATE INDEX ix_executions_approval_pending ON public.executions USING btree (approval_pending);

CREATE INDEX ix_executions_created_at ON public.executions USING btree (created_at);

CREATE INDEX ix_executions_created_by ON public.executions USING btree (created_by);

CREATE INDEX ix_executions_created_by_created_at ON public.executions USING btree (created_by, created_at);

CREATE INDEX ix_executions_deleted_at ON public.executions USING btree (deleted_at);

CREATE INDEX ix_executions_deleted_by ON public.executions USING btree (deleted_by);

CREATE INDEX ix_executions_id ON public.executions USING btree (id);

CREATE INDEX ix_executions_interface ON public.executions USING btree (interface);

CREATE INDEX ix_executions_labels ON public.executions USING gin (labels);

CREATE INDEX ix_executions_mode ON public.executions USING btree (mode);

CREATE INDEX ix_executions_project_id ON public.executions USING btree (project_id);

CREATE INDEX ix_executions_retried_from_execution_id ON public.executions USING btree (retried_from_execution_id);

CREATE INDEX ix_executions_status ON public.executions USING btree (status);

CREATE UNIQUE INDEX ix_executions_temporal_workflow_id ON public.executions USING btree (temporal_workflow_id);

CREATE INDEX ix_executions_trigger_type ON public.executions USING btree (trigger_type);

CREATE INDEX ix_executions_updated_at ON public.executions USING btree (updated_at);

CREATE INDEX ix_executions_updated_by ON public.executions USING btree (updated_by);

CREATE INDEX ix_executions_workflow_id ON public.executions USING btree (workflow_id);

CREATE INDEX ix_executions_workflow_id_status ON public.executions USING btree (workflow_id, status);

CREATE INDEX ix_file_metadata_created_at ON public.file_metadata USING btree (created_at);

CREATE INDEX ix_file_metadata_filename ON public.file_metadata USING btree (filename);

CREATE INDEX ix_file_metadata_id ON public.file_metadata USING btree (id);

CREATE INDEX ix_file_metadata_project_id ON public.file_metadata USING btree (project_id);

CREATE INDEX ix_file_metadata_status ON public.file_metadata USING btree (status);

CREATE INDEX ix_file_metadata_updated_at ON public.file_metadata USING btree (updated_at);

CREATE INDEX ix_groups_created_at ON public.groups USING btree (created_at);

CREATE INDEX ix_groups_deleted_at ON public.groups USING btree (deleted_at);

CREATE INDEX ix_groups_deleted_by ON public.groups USING btree (deleted_by);

CREATE INDEX ix_groups_id ON public.groups USING btree (id);

CREATE INDEX ix_groups_is_builtin ON public.groups USING btree (is_builtin);

CREATE INDEX ix_groups_name ON public.groups USING btree (name);

CREATE UNIQUE INDEX ix_groups_name_unique ON public.groups USING btree (name) WHERE (deleted_at IS NULL);

CREATE INDEX ix_groups_source ON public.groups USING btree (source);

CREATE INDEX ix_groups_updated_at ON public.groups USING btree (updated_at);

CREATE INDEX ix_identity_providers_created_at ON public.identity_providers USING btree (created_at);

CREATE INDEX ix_identity_providers_created_at_id ON public.identity_providers USING btree (created_at, id);

CREATE INDEX ix_identity_providers_created_by ON public.identity_providers USING btree (created_by);

CREATE INDEX ix_identity_providers_enabled ON public.identity_providers USING btree (enabled);

CREATE INDEX ix_identity_providers_id ON public.identity_providers USING btree (id);

CREATE INDEX ix_identity_providers_name ON public.identity_providers USING btree (name);

CREATE INDEX ix_identity_providers_secret_id ON public.identity_providers USING btree (secret_id);

CREATE INDEX ix_identity_providers_updated_at ON public.identity_providers USING btree (updated_at);

CREATE INDEX ix_identity_providers_updated_by ON public.identity_providers USING btree (updated_by);

CREATE INDEX ix_idp_group_mapping_entries_identity_provider_id ON public.idp_group_mapping_entries USING btree (identity_provider_id);

CREATE INDEX ix_idp_group_mapping_entries_nexus_group_id ON public.idp_group_mapping_entries USING btree (nexus_group_id);

CREATE INDEX ix_integration_project_assignments_integration_id ON public.integration_project_assignments USING btree (integration_id);

CREATE INDEX ix_integration_project_assignments_project_id ON public.integration_project_assignments USING btree (project_id);

CREATE INDEX ix_integrations_created_at ON public.integrations USING btree (created_at);

CREATE INDEX ix_integrations_created_at_id ON public.integrations USING btree (created_at, id);

CREATE INDEX ix_integrations_created_by ON public.integrations USING btree (created_by);

CREATE INDEX ix_integrations_enabled ON public.integrations USING btree (enabled);

CREATE INDEX ix_integrations_id ON public.integrations USING btree (id);

CREATE INDEX ix_integrations_integration_type ON public.integrations USING btree (integration_type);

CREATE INDEX ix_integrations_labels ON public.integrations USING gin (labels);

CREATE INDEX ix_integrations_last_refreshed_at ON public.integrations USING btree (last_refreshed_at);

CREATE INDEX ix_integrations_last_validated_at ON public.integrations USING btree (last_validated_at);

CREATE INDEX ix_integrations_name ON public.integrations USING btree (name);

CREATE INDEX ix_integrations_scope ON public.integrations USING btree (scope);

CREATE INDEX ix_integrations_updated_at ON public.integrations USING btree (updated_at);

CREATE INDEX ix_integrations_updated_by ON public.integrations USING btree (updated_by);

CREATE INDEX ix_invocations_created_at ON public.invocations USING btree (created_at);

CREATE INDEX ix_invocations_created_by ON public.invocations USING btree (created_by);

CREATE INDEX ix_invocations_created_by_status ON public.invocations USING btree (created_by, status);

CREATE INDEX ix_invocations_id ON public.invocations USING btree (id);

CREATE INDEX ix_invocations_model_name ON public.invocations USING btree (model_name);

CREATE INDEX ix_invocations_project_id ON public.invocations USING btree (project_id);

CREATE INDEX ix_invocations_session_id ON public.invocations USING btree (session_id);

CREATE INDEX ix_invocations_status ON public.invocations USING btree (status);

CREATE INDEX ix_invocations_trace_events_gin ON public.invocations USING gin (trace_events);

CREATE INDEX ix_invocations_updated_at ON public.invocations USING btree (updated_at);

CREATE INDEX ix_invocations_updated_by ON public.invocations USING btree (updated_by);

CREATE INDEX ix_llm_models_created_at ON public.llm_models USING btree (created_at);

CREATE INDEX ix_llm_models_enabled ON public.llm_models USING btree (enabled);

CREATE INDEX ix_llm_models_id ON public.llm_models USING btree (id);

CREATE INDEX ix_llm_models_integration_id ON public.llm_models USING btree (integration_id);

CREATE INDEX ix_llm_models_integration_id_created_at_id ON public.llm_models USING btree (integration_id, created_at, id);

CREATE INDEX ix_llm_models_updated_at ON public.llm_models USING btree (updated_at);

CREATE INDEX ix_policies_created_at ON public.policies USING btree (created_at);

CREATE INDEX ix_policies_id ON public.policies USING btree (id);

CREATE INDEX ix_policies_is_builtin ON public.policies USING btree (is_builtin);

CREATE INDEX ix_policies_name ON public.policies USING btree (name);

CREATE UNIQUE INDEX ix_policies_name_global_unique ON public.policies USING btree (name) WHERE (project_id IS NULL);

CREATE UNIQUE INDEX ix_policies_name_project_unique ON public.policies USING btree (name, project_id) WHERE (project_id IS NOT NULL);

CREATE INDEX ix_policies_project_id ON public.policies USING btree (project_id);

CREATE INDEX ix_policies_scope ON public.policies USING btree (scope);

CREATE INDEX ix_policies_updated_at ON public.policies USING btree (updated_at);

CREATE INDEX ix_principals_principal_type ON public.principals USING btree (principal_type);

CREATE INDEX ix_projects_created_at ON public.projects USING btree (created_at);

CREATE INDEX ix_projects_deleted_at ON public.projects USING btree (deleted_at);

CREATE INDEX ix_projects_deleted_by ON public.projects USING btree (deleted_by);

CREATE INDEX ix_projects_id ON public.projects USING btree (id);

CREATE INDEX ix_projects_is_builtin ON public.projects USING btree (is_builtin);

CREATE INDEX ix_projects_is_default ON public.projects USING btree (is_default);

CREATE INDEX ix_projects_name ON public.projects USING btree (name);

CREATE UNIQUE INDEX ix_projects_name_unique ON public.projects USING btree (name) WHERE (deleted_at IS NULL);

CREATE INDEX ix_projects_updated_at ON public.projects USING btree (updated_at);

CREATE UNIQUE INDEX ix_ra_group_role_global ON public.role_assignments USING btree (group_id, role_name) WHERE ((project_id IS NULL) AND (group_id IS NOT NULL));

CREATE UNIQUE INDEX ix_ra_group_role_project ON public.role_assignments USING btree (group_id, role_name, project_id) WHERE ((project_id IS NOT NULL) AND (group_id IS NOT NULL));

CREATE UNIQUE INDEX ix_ra_principal_role_global ON public.role_assignments USING btree (principal_id, role_name) WHERE ((project_id IS NULL) AND (principal_id IS NOT NULL));

CREATE UNIQUE INDEX ix_ra_principal_role_project ON public.role_assignments USING btree (principal_id, role_name, project_id) WHERE ((project_id IS NOT NULL) AND (principal_id IS NOT NULL));

CREATE INDEX ix_rate_limits_created_at ON public.rate_limits USING btree (created_at);

CREATE INDEX ix_rate_limits_created_by ON public.rate_limits USING btree (created_by);

CREATE INDEX ix_rate_limits_id ON public.rate_limits USING btree (id);

CREATE INDEX ix_rate_limits_target_id ON public.rate_limits USING btree (target_id);

CREATE INDEX ix_rate_limits_target_type ON public.rate_limits USING btree (target_type);

CREATE INDEX ix_rate_limits_updated_at ON public.rate_limits USING btree (updated_at);

CREATE INDEX ix_rate_limits_updated_by ON public.rate_limits USING btree (updated_by);

CREATE INDEX ix_refresh_sessions_expires_at ON public.refresh_sessions USING btree (expires_at);

CREATE INDEX ix_refresh_sessions_identity_id ON public.refresh_sessions USING btree (identity_id) WHERE (revoked_at IS NULL);

CREATE INDEX ix_refresh_sessions_idp_id ON public.refresh_sessions USING btree (idp_id) WHERE (revoked_at IS NULL);

CREATE INDEX ix_refresh_sessions_user_id ON public.refresh_sessions USING btree (user_id) WHERE (revoked_at IS NULL);

CREATE INDEX ix_role_assignments_created_at ON public.role_assignments USING btree (created_at);

CREATE INDEX ix_role_assignments_group_id ON public.role_assignments USING btree (group_id);

CREATE INDEX ix_role_assignments_id ON public.role_assignments USING btree (id);

CREATE INDEX ix_role_assignments_is_builtin ON public.role_assignments USING btree (is_builtin);

CREATE INDEX ix_role_assignments_principal_id ON public.role_assignments USING btree (principal_id);

CREATE INDEX ix_role_assignments_project_id ON public.role_assignments USING btree (project_id);

CREATE INDEX ix_role_assignments_role_name ON public.role_assignments USING btree (role_name);

CREATE INDEX ix_role_assignments_updated_at ON public.role_assignments USING btree (updated_at);

CREATE INDEX ix_roles_created_at ON public.roles USING btree (created_at);

CREATE INDEX ix_roles_id ON public.roles USING btree (id);

CREATE INDEX ix_roles_is_builtin ON public.roles USING btree (is_builtin);

CREATE INDEX ix_roles_name ON public.roles USING btree (name);

CREATE UNIQUE INDEX ix_roles_name_global_unique ON public.roles USING btree (name) WHERE (project_id IS NULL);

CREATE UNIQUE INDEX ix_roles_name_project_unique ON public.roles USING btree (name, project_id) WHERE (project_id IS NOT NULL);

CREATE INDEX ix_roles_project_id ON public.roles USING btree (project_id);

CREATE INDEX ix_roles_scope ON public.roles USING btree (scope);

CREATE INDEX ix_roles_updated_at ON public.roles USING btree (updated_at);

CREATE INDEX ix_runtime_settings_category ON public.runtime_settings USING btree (category);

CREATE INDEX ix_runtime_settings_created_at ON public.runtime_settings USING btree (created_at);

CREATE INDEX ix_runtime_settings_id ON public.runtime_settings USING btree (id);

CREATE INDEX ix_runtime_settings_key ON public.runtime_settings USING btree (key);

CREATE INDEX ix_runtime_settings_name ON public.runtime_settings USING btree (name);

CREATE INDEX ix_runtime_settings_updated_at ON public.runtime_settings USING btree (updated_at);

CREATE INDEX ix_runtime_settings_value_type ON public.runtime_settings USING btree (value_type);

CREATE INDEX ix_sa_credentials_created_at_id ON public.service_account_credentials USING btree (created_at, id);

CREATE UNIQUE INDEX ix_sa_credentials_identifier_unique ON public.service_account_credentials USING btree (identifier);

CREATE INDEX ix_sa_credentials_sa_id_type ON public.service_account_credentials USING btree (service_account_id, credential_type);

CREATE INDEX ix_service_account_credentials_created_at ON public.service_account_credentials USING btree (created_at);

CREATE INDEX ix_service_account_credentials_created_by ON public.service_account_credentials USING btree (created_by);

CREATE INDEX ix_service_account_credentials_id ON public.service_account_credentials USING btree (id);

CREATE INDEX ix_service_account_credentials_identifier ON public.service_account_credentials USING btree (identifier);

CREATE INDEX ix_service_account_credentials_service_account_id ON public.service_account_credentials USING btree (service_account_id);

CREATE INDEX ix_service_account_credentials_status ON public.service_account_credentials USING btree (status);

CREATE INDEX ix_service_account_credentials_updated_at ON public.service_account_credentials USING btree (updated_at);

CREATE INDEX ix_service_account_credentials_updated_by ON public.service_account_credentials USING btree (updated_by);

CREATE INDEX ix_service_accounts_created_at ON public.service_accounts USING btree (created_at);

CREATE INDEX ix_service_accounts_created_at_id ON public.service_accounts USING btree (created_at, id);

CREATE INDEX ix_service_accounts_created_by ON public.service_accounts USING btree (created_by);

CREATE INDEX ix_service_accounts_id ON public.service_accounts USING btree (id);

CREATE INDEX ix_service_accounts_name ON public.service_accounts USING btree (name);

CREATE INDEX ix_service_accounts_project_id ON public.service_accounts USING btree (project_id);

CREATE INDEX ix_service_accounts_status ON public.service_accounts USING btree (status);

CREATE INDEX ix_service_accounts_updated_at ON public.service_accounts USING btree (updated_at);

CREATE INDEX ix_service_accounts_updated_by ON public.service_accounts USING btree (updated_by);

CREATE INDEX ix_setting_categories_created_at ON public.setting_categories USING btree (created_at);

CREATE INDEX ix_setting_categories_id ON public.setting_categories USING btree (id);

CREATE INDEX ix_setting_categories_name ON public.setting_categories USING btree (name);

CREATE UNIQUE INDEX ix_setting_categories_slug ON public.setting_categories USING btree (slug);

CREATE INDEX ix_setting_categories_updated_at ON public.setting_categories USING btree (updated_at);

CREATE INDEX ix_token_usage_records_created_at ON public.token_usage_records USING btree (created_at);

CREATE INDEX ix_token_usage_records_id ON public.token_usage_records USING btree (id);

CREATE UNIQUE INDEX ix_token_usage_records_invocation_id_unique ON public.token_usage_records USING btree (invocation_id) WHERE (invocation_id IS NOT NULL);

CREATE INDEX ix_token_usage_records_request_timestamp ON public.token_usage_records USING btree (request_timestamp);

CREATE INDEX ix_token_usage_records_updated_at ON public.token_usage_records USING btree (updated_at);

CREATE INDEX ix_token_usage_records_user_id ON public.token_usage_records USING btree (user_id);

CREATE INDEX ix_tool_executions_created_at ON public.tool_executions USING btree (created_at);

CREATE INDEX ix_tool_executions_created_by ON public.tool_executions USING btree (created_by);

CREATE INDEX ix_tool_executions_execution_start ON public.tool_executions USING btree (execution_start);

CREATE INDEX ix_tool_executions_id ON public.tool_executions USING btree (id);

CREATE INDEX ix_tool_executions_integration_id ON public.tool_executions USING btree (integration_id);

CREATE INDEX ix_tool_executions_tool_id ON public.tool_executions USING btree (tool_id);

CREATE INDEX ix_tool_executions_updated_at ON public.tool_executions USING btree (updated_at);

CREATE INDEX ix_tool_executions_updated_by ON public.tool_executions USING btree (updated_by);

CREATE INDEX ix_tool_executions_user_id ON public.tool_executions USING btree (user_id);

CREATE INDEX ix_tool_parameters_created_at ON public.tool_parameters USING btree (created_at);

CREATE INDEX ix_tool_parameters_id ON public.tool_parameters USING btree (id);

CREATE INDEX ix_tool_parameters_tool_id ON public.tool_parameters USING btree (tool_id);

CREATE INDEX ix_tool_parameters_updated_at ON public.tool_parameters USING btree (updated_at);

CREATE INDEX ix_tools_created_at ON public.tools USING btree (created_at);

CREATE INDEX ix_tools_created_at_id ON public.tools USING btree (created_at, id);

CREATE INDEX ix_tools_created_by ON public.tools USING btree (created_by);

CREATE INDEX ix_tools_enabled ON public.tools USING btree (enabled);

CREATE INDEX ix_tools_id ON public.tools USING btree (id);

CREATE INDEX ix_tools_integration_id ON public.tools USING btree (integration_id);

CREATE INDEX ix_tools_integration_id_created_at_id ON public.tools USING btree (integration_id, created_at, id);

CREATE INDEX ix_tools_last_executed_at ON public.tools USING btree (last_executed_at);

CREATE INDEX ix_tools_last_refreshed_at ON public.tools USING btree (last_refreshed_at);

CREATE INDEX ix_tools_name ON public.tools USING btree (name);

CREATE INDEX ix_tools_namespaced_name ON public.tools USING btree (namespaced_name);

CREATE INDEX ix_tools_status ON public.tools USING btree (status);

CREATE INDEX ix_tools_updated_at ON public.tools USING btree (updated_at);

CREATE INDEX ix_tools_updated_by ON public.tools USING btree (updated_by);

CREATE INDEX ix_usage_counters_counter_type ON public.usage_counters USING btree (counter_type);

CREATE INDEX ix_usage_counters_created_at ON public.usage_counters USING btree (created_at);

CREATE INDEX ix_usage_counters_created_by ON public.usage_counters USING btree (created_by);

CREATE INDEX ix_usage_counters_id ON public.usage_counters USING btree (id);

CREATE INDEX ix_usage_counters_integration_id ON public.usage_counters USING btree (integration_id);

CREATE INDEX ix_usage_counters_time_window ON public.usage_counters USING btree (time_window);

CREATE INDEX ix_usage_counters_tool_id ON public.usage_counters USING btree (tool_id);

CREATE INDEX ix_usage_counters_updated_at ON public.usage_counters USING btree (updated_at);

CREATE INDEX ix_usage_counters_updated_by ON public.usage_counters USING btree (updated_by);

CREATE INDEX ix_usage_counters_user_id ON public.usage_counters USING btree (user_id);

CREATE INDEX ix_usage_counters_window_end ON public.usage_counters USING btree (window_end);

CREATE INDEX ix_usage_counters_window_start ON public.usage_counters USING btree (window_start);

CREATE INDEX ix_user_identities_id ON public.user_identities USING btree (id);

CREATE INDEX ix_user_identities_identity_provider_id ON public.user_identities USING btree (identity_provider_id);

CREATE INDEX ix_user_identities_user_id ON public.user_identities USING btree (user_id);

CREATE INDEX ix_user_token_configs_created_at ON public.user_token_configs USING btree (created_at);

CREATE INDEX ix_user_token_configs_id ON public.user_token_configs USING btree (id);

CREATE INDEX ix_user_token_configs_updated_at ON public.user_token_configs USING btree (updated_at);

CREATE UNIQUE INDEX ix_user_token_configs_user_id ON public.user_token_configs USING btree (user_id);

CREATE INDEX ix_users_auth_type ON public.users USING btree (auth_type);

CREATE INDEX ix_users_created_at ON public.users USING btree (created_at);

CREATE INDEX ix_users_deleted_at ON public.users USING btree (deleted_at);

CREATE INDEX ix_users_deleted_by ON public.users USING btree (deleted_by);

CREATE INDEX ix_users_email ON public.users USING btree (email);

CREATE UNIQUE INDEX ix_users_email_unique ON public.users USING btree (email) WHERE ((email IS NOT NULL) AND (deleted_at IS NULL));

CREATE INDEX ix_users_id ON public.users USING btree (id);

CREATE INDEX ix_users_is_builtin ON public.users USING btree (is_builtin);

CREATE INDEX ix_users_is_enabled ON public.users USING btree (is_enabled);

CREATE INDEX ix_users_updated_at ON public.users USING btree (updated_at);

CREATE INDEX ix_users_username ON public.users USING btree (username);

CREATE UNIQUE INDEX ix_users_username_unique ON public.users USING btree (username) WHERE (deleted_at IS NULL);

CREATE INDEX ix_webhook_triggers_created_at ON public.webhook_triggers USING btree (created_at);

CREATE INDEX ix_webhook_triggers_id ON public.webhook_triggers USING btree (id);

CREATE INDEX ix_webhook_triggers_is_enabled ON public.webhook_triggers USING btree (is_enabled);

CREATE INDEX ix_webhook_triggers_labels ON public.webhook_triggers USING gin (labels);

CREATE INDEX ix_webhook_triggers_trigger_type ON public.webhook_triggers USING btree (trigger_type);

CREATE UNIQUE INDEX ix_webhook_triggers_type_path_unique ON public.webhook_triggers USING btree (trigger_type, webhook_path);

CREATE INDEX ix_webhook_triggers_updated_at ON public.webhook_triggers USING btree (updated_at);

CREATE INDEX ix_webhook_triggers_workflow_id ON public.webhook_triggers USING btree (workflow_id);

CREATE INDEX ix_webhook_triggers_workflow_id_enabled ON public.webhook_triggers USING btree (workflow_id, is_enabled);

CREATE INDEX ix_wf_publish_events_actor_id ON public.workflow_publish_events USING btree (actor_id);

CREATE INDEX ix_wf_publish_events_version_id ON public.workflow_publish_events USING btree (version_id);

CREATE INDEX ix_wf_publish_events_workflow_id ON public.workflow_publish_events USING btree (workflow_id);

CREATE INDEX ix_workflow_publish_events_created_at ON public.workflow_publish_events USING btree (created_at);

CREATE INDEX ix_workflow_publish_events_id ON public.workflow_publish_events USING btree (id);

CREATE INDEX ix_workflow_publish_events_updated_at ON public.workflow_publish_events USING btree (updated_at);

CREATE INDEX ix_workflow_versions_created_at ON public.workflow_versions USING btree (created_at);

CREATE INDEX ix_workflow_versions_created_by ON public.workflow_versions USING btree (created_by);

CREATE INDEX ix_workflow_versions_deleted_at ON public.workflow_versions USING btree (deleted_at);

CREATE INDEX ix_workflow_versions_deleted_by ON public.workflow_versions USING btree (deleted_by);

CREATE INDEX ix_workflow_versions_id ON public.workflow_versions USING btree (id);

CREATE INDEX ix_workflow_versions_schema_version ON public.workflow_versions USING btree (schema_version);

CREATE INDEX ix_workflow_versions_updated_at ON public.workflow_versions USING btree (updated_at);

CREATE INDEX ix_workflow_versions_updated_by ON public.workflow_versions USING btree (updated_by);

CREATE INDEX ix_workflow_versions_version ON public.workflow_versions USING btree (version);

CREATE INDEX ix_workflow_versions_workflow_created ON public.workflow_versions USING btree (workflow_id, created_at);

CREATE INDEX ix_workflow_versions_workflow_id ON public.workflow_versions USING btree (workflow_id);

CREATE UNIQUE INDEX ix_workflow_versions_workflow_version ON public.workflow_versions USING btree (workflow_id, version);

CREATE INDEX ix_workflows_created_at ON public.workflows USING btree (created_at);

CREATE INDEX ix_workflows_created_by ON public.workflows USING btree (created_by);

CREATE INDEX ix_workflows_created_by_enabled ON public.workflows USING btree (created_by, is_enabled);

CREATE INDEX ix_workflows_current_version ON public.workflows USING btree (current_version);

CREATE INDEX ix_workflows_deleted_at ON public.workflows USING btree (deleted_at);

CREATE INDEX ix_workflows_deleted_by ON public.workflows USING btree (deleted_by);

CREATE INDEX ix_workflows_id ON public.workflows USING btree (id);

CREATE INDEX ix_workflows_is_builtin ON public.workflows USING btree (is_builtin);

CREATE INDEX ix_workflows_is_enabled ON public.workflows USING btree (is_enabled);

CREATE INDEX ix_workflows_labels ON public.workflows USING gin (labels);

CREATE INDEX ix_workflows_name ON public.workflows USING btree (name);

CREATE UNIQUE INDEX ix_workflows_name_project_unique ON public.workflows USING btree (name, project_id) WHERE (deleted_at IS NULL);

CREATE INDEX ix_workflows_project_id ON public.workflows USING btree (project_id);

CREATE INDEX ix_workflows_published_version_id ON public.workflows USING btree (published_version_id);

CREATE INDEX ix_workflows_updated_at ON public.workflows USING btree (updated_at);

CREATE INDEX ix_workflows_updated_by ON public.workflows USING btree (updated_by);

CREATE INDEX ix_wt_sa_service_account_id ON public.webhook_trigger_service_accounts USING btree (service_account_id);

ALTER TABLE ONLY public.activity_execution
    ADD CONSTRAINT activity_execution_execution_id_fkey FOREIGN KEY (execution_id) REFERENCES public.executions(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.approval_approver_groups
    ADD CONSTRAINT approval_approver_groups_approval_id_fkey FOREIGN KEY (approval_id) REFERENCES public.approval_requests(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.approval_approver_groups
    ADD CONSTRAINT approval_approver_groups_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.approval_approver_users
    ADD CONSTRAINT approval_approver_users_approval_id_fkey FOREIGN KEY (approval_id) REFERENCES public.approval_requests(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.approval_approver_users
    ADD CONSTRAINT approval_approver_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_decided_by_fkey FOREIGN KEY (decided_by) REFERENCES public.principals(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_credential_type_id_fkey FOREIGN KEY (credential_type_id) REFERENCES public.credential_types(id);

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.secrets(id);

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.encrypted_secrets
    ADD CONSTRAINT encrypted_secrets_secret_id_fkey FOREIGN KEY (secret_id) REFERENCES public.secrets(id);

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT executions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT executions_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT executions_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT executions_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT executions_workflow_version_id_fkey FOREIGN KEY (workflow_version_id) REFERENCES public.workflow_versions(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT fk_approval_requests_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT fk_credentials_project_id FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT fk_executions_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.executions
    ADD CONSTRAINT fk_executions_retried_from_execution_id FOREIGN KEY (retried_from_execution_id) REFERENCES public.executions(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.file_metadata
    ADD CONSTRAINT fk_file_metadata_project_id FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.identity_providers
    ADD CONSTRAINT fk_identity_providers_secret_id FOREIGN KEY (secret_id) REFERENCES public.secrets(id);

ALTER TABLE ONLY public.invocations
    ADD CONSTRAINT fk_invocations_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.llm_models
    ADD CONSTRAINT fk_llm_models_integration_id FOREIGN KEY (integration_id) REFERENCES public.integrations(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT fk_ra_group_id_groups FOREIGN KEY (group_id) REFERENCES public.groups(id);

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT fk_ra_principal_id_principals FOREIGN KEY (principal_id) REFERENCES public.principals(id);

ALTER TABLE ONLY public.runtime_settings
    ADD CONSTRAINT fk_runtime_settings_category_setting_categories FOREIGN KEY (category) REFERENCES public.setting_categories(slug);

ALTER TABLE ONLY public.token_usage_records
    ADD CONSTRAINT fk_token_usage_records_invocation_id FOREIGN KEY (invocation_id) REFERENCES public.invocations(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.tool_executions
    ADD CONSTRAINT fk_tool_executions_integration_id FOREIGN KEY (integration_id) REFERENCES public.integrations(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.tools
    ADD CONSTRAINT fk_tools_integration_id FOREIGN KEY (integration_id) REFERENCES public.integrations(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.usage_counters
    ADD CONSTRAINT fk_usage_counters_integration_id FOREIGN KEY (integration_id) REFERENCES public.integrations(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT fk_workflows_project_id_projects FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.identity_providers
    ADD CONSTRAINT identity_providers_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.identity_providers
    ADD CONSTRAINT identity_providers_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.idp_group_mapping_entries
    ADD CONSTRAINT idp_group_mapping_entries_identity_provider_id_fkey FOREIGN KEY (identity_provider_id) REFERENCES public.identity_providers(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.idp_group_mapping_entries
    ADD CONSTRAINT idp_group_mapping_entries_nexus_group_id_fkey FOREIGN KEY (nexus_group_id) REFERENCES public.groups(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.integration_project_assignments
    ADD CONSTRAINT integration_project_assignments_integration_id_fkey FOREIGN KEY (integration_id) REFERENCES public.integrations(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.integration_project_assignments
    ADD CONSTRAINT integration_project_assignments_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_management_credential_id_fkey FOREIGN KEY (management_credential_id) REFERENCES public.credentials(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.invocations
    ADD CONSTRAINT invocations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.invocations
    ADD CONSTRAINT invocations_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.rate_limits
    ADD CONSTRAINT rate_limits_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.rate_limits
    ADD CONSTRAINT rate_limits_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.refresh_sessions
    ADD CONSTRAINT refresh_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.role_assignments
    ADD CONSTRAINT role_assignments_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.service_account_credentials
    ADD CONSTRAINT service_account_credentials_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.service_account_credentials
    ADD CONSTRAINT service_account_credentials_service_account_id_fkey FOREIGN KEY (service_account_id) REFERENCES public.service_accounts(id);

ALTER TABLE ONLY public.service_account_credentials
    ADD CONSTRAINT service_account_credentials_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.service_accounts
    ADD CONSTRAINT service_accounts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.service_accounts
    ADD CONSTRAINT service_accounts_id_fkey FOREIGN KEY (id) REFERENCES public.principals(id);

ALTER TABLE ONLY public.service_accounts
    ADD CONSTRAINT service_accounts_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);

ALTER TABLE ONLY public.service_accounts
    ADD CONSTRAINT service_accounts_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.token_usage_records
    ADD CONSTRAINT token_usage_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.tool_executions
    ADD CONSTRAINT tool_executions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.tool_executions
    ADD CONSTRAINT tool_executions_tool_id_fkey FOREIGN KEY (tool_id) REFERENCES public.tools(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.tool_executions
    ADD CONSTRAINT tool_executions_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.tool_parameters
    ADD CONSTRAINT tool_parameters_tool_id_fkey FOREIGN KEY (tool_id) REFERENCES public.tools(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tools
    ADD CONSTRAINT tools_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.tools
    ADD CONSTRAINT tools_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.usage_counters
    ADD CONSTRAINT usage_counters_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.usage_counters
    ADD CONSTRAINT usage_counters_tool_id_fkey FOREIGN KEY (tool_id) REFERENCES public.tools(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.usage_counters
    ADD CONSTRAINT usage_counters_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.user_groups
    ADD CONSTRAINT user_groups_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_groups
    ADD CONSTRAINT user_groups_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_identities
    ADD CONSTRAINT user_identities_identity_provider_id_fkey FOREIGN KEY (identity_provider_id) REFERENCES public.identity_providers(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_identities
    ADD CONSTRAINT user_identities_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_idp_groups
    ADD CONSTRAINT user_idp_groups_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_idp_groups
    ADD CONSTRAINT user_idp_groups_identity_provider_id_fkey FOREIGN KEY (identity_provider_id) REFERENCES public.identity_providers(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_idp_groups
    ADD CONSTRAINT user_idp_groups_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_token_configs
    ADD CONSTRAINT user_token_configs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_id_fkey FOREIGN KEY (id) REFERENCES public.principals(id);

ALTER TABLE ONLY public.webhook_trigger_service_accounts
    ADD CONSTRAINT webhook_trigger_service_accounts_service_account_id_fkey FOREIGN KEY (service_account_id) REFERENCES public.service_accounts(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.webhook_trigger_service_accounts
    ADD CONSTRAINT webhook_trigger_service_accounts_webhook_trigger_id_fkey FOREIGN KEY (webhook_trigger_id) REFERENCES public.webhook_triggers(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.webhook_triggers
    ADD CONSTRAINT webhook_triggers_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.workflow_publish_events
    ADD CONSTRAINT workflow_publish_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.principals(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.workflow_publish_events
    ADD CONSTRAINT workflow_publish_events_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.workflow_versions(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.workflow_publish_events
    ADD CONSTRAINT workflow_publish_events_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.workflow_versions
    ADD CONSTRAINT workflow_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.workflow_versions
    ADD CONSTRAINT workflow_versions_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.workflow_versions
    ADD CONSTRAINT workflow_versions_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.workflow_versions
    ADD CONSTRAINT workflow_versions_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id);

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.principals(id);

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_published_version_id_fkey FOREIGN KEY (published_version_id) REFERENCES public.workflow_versions(id);

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.principals(id);
