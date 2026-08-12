# OpenAPI Schema vs Implementation Analysis

This document analyzes discrepancies between the OpenAPI schema documentation and the current RFC 9457 compliant error handling implementation.

## Current Implementation Changes

Our error handling implementation now returns:
- **RFC 9457 compliant responses** with `Content-Type: application/problem+json`
- **Proper HTTP status codes** (409 for conflicts, 422 for validation errors)
- **Centralized global error handlers** that ensure consistency

## Schema vs Implementation Discrepancies

### 1. Workflows API (`/workflows/openapi.yaml`)

#### POST /workflows (Create Workflow)
**Schema Documents:**
- `400`: Invalid workflow definition  
- `422`: Validation error (e.g., invalid label types)

**Current Implementation:**
- `409`: Name conflicts (`WorkflowNameConflictError`) ❌ **NOT DOCUMENTED**
- `422`: Pydantic validation errors ✅ **MATCHES**

**Issue:** Schema missing `409` status code for duplicate workflow names.

#### PATCH /workflows/{id} (Update Workflow)  
**Schema Documents:**
- `400`: Invalid workflow definition or validation error
- `422`: Validation error (e.g., invalid label types)
- `404`: Workflow not found

**Current Implementation:**
- `409`: Name conflicts (`WorkflowNameConflictError`) ❌ **NOT DOCUMENTED**
- `422`: Pydantic validation errors ✅ **MATCHES**
- `404`: Not found ✅ **MATCHES**

**Issue:** Schema missing `409` status code for name conflicts during updates.

### 2. Invocations API (`/invocations/openapi.yaml`)

#### POST /invocations (Create Invocation)
**Schema Documents:**
- `400`: Bad Request - Validation or file processing error
- `401`: Unauthorized
- `500`: Internal Server Error
- `503`: Service Unavailable - LLM provider not configured

**Current Implementation:**
- `400`: File validation errors (`FileValidationError`) ✅ **MATCHES**
- `503`: LLM configuration errors ✅ **MATCHES**

**Status:** ✅ **SCHEMAS MATCH IMPLEMENTATION**

### 3. Files API (`/files/openapi.yaml`)

#### POST /files (Upload Files)
**Schema Documents:**
- `400`: Bad Request - Validation error
- `401`: Unauthorized  
- `500`: Internal Server Error - Storage failure

**Current Implementation:**
- `400`: File validation errors (`FileValidationError`) ✅ **MATCHES**
- `500`: Storage failures (OSError) ✅ **MATCHES**

**Status:** ✅ **SCHEMAS MATCH IMPLEMENTATION**

### 4. Tool Manager API (`/tool_manager/openapi.yaml`)

#### POST /tool_providers (Register Tool Provider)
**Schema Documents:**
- `201`: Provider registered successfully
- `400`: Invalid provider configuration
- `403`: Admin access required

**Current Implementation:**
- `409`: Name conflicts (`ProviderNameConflictError`) ❌ **NOT DOCUMENTED**
- `400`: Invalid provider configuration ✅ **MATCHES**

**Issue:** Schema missing `409` status code for duplicate provider names.

### 5. Executions API (`/executions_openapi.yaml`)

#### POST /executions (Create Execution)
**Schema Documents:**
- `201`: Execution started
- `404`: Workflow not found

**Current Implementation:**
- `404`: Workflow not found (`WorkflowNotFoundError`) ✅ **MATCHES**
- `400`: Workflow disabled (`WorkflowDisabledError`) ❌ **NOT DOCUMENTED**

**Issue:** Schema missing `400` status code for disabled workflows.

## Error Response Format Discrepancy

### Current Schema Format (Legacy)
```json
{
  "error": "validation_error",
  "message": "Invalid request parameters",
  "details": "Field 'name' must be between 1 and 255 characters"
}
```

### Current Implementation Format (RFC 9457)
```json
{
  "type": "https://api.example.com/errors/validation-error",
  "title": "Validation Error",
  "detail": "Field 'name' must be between 1 and 255 characters",
  "code": "VALIDATION_ERROR",
  "retryable": false,
  "instance": "/api/v1/workflows"
}
```

**Content-Type:** `application/problem+json` (not `application/json`)

## Required Schema Updates

### 1. Add Missing Status Codes

#### Workflows API
```yaml
# Add to POST /workflows and PATCH /workflows/{id}
'409':
  description: Name conflict - workflow with this name already exists
  content:
    application/problem+json:
      schema:
        $ref: '../base/shared-resources.openapi.yaml#/components/schemas/ErrorData'
      example:
        type: "https://api.example.com/errors/name-conflict"
        title: "Workflow Name Conflict"
        detail: "A workflow with this name already exists"
        code: "WORKFLOW_NAME_CONFLICT"
        retryable: false
        instance: "/api/v1/workflows"
```

#### Tool Manager API  
```yaml
# Add to POST /tool_providers
'409':
  description: Name conflict - provider with this name already exists
  content:
    application/problem+json:
      schema:
        $ref: '../base/shared-resources.openapi.yaml#/components/schemas/ErrorData'
```

#### Executions API
```yaml
# Add to POST /executions  
'400':
  description: Workflow is disabled
  content:
    application/problem+json:
      schema:
        $ref: '../base/shared-resources.openapi.yaml#/components/schemas/ErrorData'
```

### 2. Update Response Content Types

**Change all error responses from:**
```yaml
content:
  application/json:
    schema:
      $ref: '#/components/schemas/Error'
```

**To:**  
```yaml
content:
  application/problem+json:
    schema:
      $ref: '../base/shared-resources.openapi.yaml#/components/schemas/ErrorData'
```

### 3. Use Existing ErrorData Schema

The RFC 9457 compliant schema **already exists** as `ErrorData` in `syntara.core.models.base.error`.

Our error handlers are already using this model:

```python
from syntara.core.models.error import ErrorData


def create_problem_details_response(...) -> JSONResponse:
    error_data = ErrorData(
        type=problem_type,
        title=title,
        detail=detail,
        code=code,
        retryable=retryable,
        instance=instance,
    )
    return JSONResponse(
        status_code=status_code,
        content=error_data.to_dict(),
        media_type="application/problem+json",
    )
```

The `ErrorData` model is already RFC 9457 compliant and includes:
- `type`: URI identifying the problem type
- `title`: Short, human-readable summary  
- `detail`: Human-readable explanation
- `code`: Machine-readable error code
- `retryable`: Whether the error is retryable
- `instance`: URI identifying the specific occurrence

**No new schema needed** - just reference the existing `ErrorData` model in OpenAPI schemas.

## Summary

### Status Codes to Add:
1. **409 Conflict** for name conflicts in:
   - POST/PATCH `/workflows`
   - POST `/tool_providers`

2. **400 Bad Request** for business logic errors in:
   - POST `/executions` (disabled workflows)

### Schema Format Updates:
1. Replace legacy `Error` schema references with existing `ErrorData` schema
2. Update `Content-Type` to `application/problem+json`  
3. Update all error response examples to RFC 9457 format using `ErrorData`

### Priority:
- **High**: Add missing 409 status codes (breaking change for consumers)
- **High**: Update error response format to use `ErrorData` (breaking change)
- **Medium**: Update examples and documentation

This brings OpenAPI documentation in line with our RFC 9457 compliant implementation and ensures API consumers have accurate expectations for error responses.
