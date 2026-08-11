# Credential Audit Events

Audit instrumentation for the credentials domain (`src/syntara/credentials/`).

## Domain Events

### CredentialLifecycleEvent

Tracks credential create, update, and delete operations.

| Field | Type | Description |
|-------|------|-------------|
| `credential_id` | UUID | Credential being acted on |
| `credential_name` | str | Name of the credential |
| `credential_type_id` | UUID | Credential type |
| `action` | str | `"created"`, `"updated"`, or `"deleted"` |
| `project_id` | UUID \| None | Owning project |
| `affected_workflow_count` | int | Workflows referencing this credential (populated on delete) |
| `enabled_changed` | bool | Whether the enabled state was toggled (on update) |
| `error_type` | str \| None | Error class name if the operation failed |

**Handler:** `CredentialLifecycleHandler`
- Category: `USER_ACTION`
- Action: `credential_created`, `credential_updated`, `credential_deleted`
- Severity: `WARNING` when deleting a credential used by workflows or toggling `enabled`; `ERROR` on failure; `INFO` otherwise
- Sets `resource_urn` as `urn:syntara:credential:{credential_id}`

### CredentialEncryptionFailureEvent

Tracks credential decryption failures during get or update operations.

| Field | Type | Description |
|-------|------|-------------|
| `credential_id` | UUID | Credential that failed to decrypt |
| `credential_name` | str | Name of the credential |
| `operation` | str | `"decrypt"` |
| `error_type` | str | Error class name |

**Handler:** `CredentialEncryptionFailureHandler`
- Category: `SECURITY_EVENT`
- Action: `credential_encryption_failure`
- Severity: `ERROR`
- Sets `resource_urn` as `urn:syntara:credential:{credential_id}`

## Instrumentation Layers

| Layer | Status | Details |
|-------|--------|---------|
| 1. Middleware | Automatic | All credential endpoints captured by `AuditMiddleware` |
| 2. `@audit` | Active | `create_credential`, `update_credential`, `delete_credential` |
| 3. CRUD | Pending | Models inherit `BaseResource`, ready for AAP-73776 |
| 4. Domain Events | Active | `CredentialLifecycleEvent`, `CredentialEncryptionFailureEvent` |

## Audit Trail Per Operation

**Credential create:** 3 events
1. `credential_created` (CredentialLifecycleEvent, USER_ACTION, INFO)
2. `credential_create` (@audit decorator, USER_ACTION)
3. `request_completed` (AuditMiddleware, 201)

**Credential delete with workflow refs:** 3 events
1. `credential_deleted` (CredentialLifecycleEvent, USER_ACTION, WARNING)
2. `credential_delete` (@audit decorator, USER_ACTION)
3. `request_completed` (AuditMiddleware, 204)

**Decryption failure during get/update:** 3 events
1. `credential_encryption_failure` (CredentialEncryptionFailureEvent, SECURITY_EVENT, ERROR)
2. `credential_create`/`credential_update` (@audit decorator, ERROR)
3. `request_completed` (AuditMiddleware, 500)
