# Error Handling Strategy

This document outlines the comprehensive error handling strategy implemented across the Syntara application to ensure all REST API responses comply with RFC 9457 Problem Details specification.

## Overview

The Syntara application implements a **centralized exception handling strategy** that provides consistent, secure, and standards-compliant error responses across all API endpoints. This approach ensures clean separation of concerns between business logic and HTTP presentation layers.

## Architecture Principles

### 1. Single Exception Boundary

The application maintains a **single exception boundary** at the FastAPI global exception handler level. This ensures:

- Consistent error response format across all endpoints
- Centralized security controls to prevent information disclosure
- Simplified maintenance and debugging
- RFC 9457 compliance for all API consumers

### 2. Clean Separation of Concerns

The error handling strategy enforces clear boundaries between architectural layers:

```
Services (Business Logic) → Domain Exceptions → Global Handlers → RFC 9457 Responses
```

## Implementation Strategy

### Services: Domain Exception Sources

**Services throw domain-specific exceptions** that represent business logic failures:

```python
# Example: Service throws domain exceptions
class WorkflowService:
    async def create_workflow(self, name: str) -> Workflow:
        if await self._name_exists(name):
            raise WorkflowNameConflictError(f"Workflow '{name}' already exists")

        try:
            return await self._create_workflow(name)
        except IntegrityError as e:
            raise WorkflowValidationError("Invalid workflow data") from e
```

**Benefits:**
- Clear business logic representation
- Testable exception scenarios
- Domain-driven error semantics

### FastAPI Routers: Exception Transparency

**Routers do NOT catch domain exceptions** and convert them to HTTPExceptions:

```python
# ✅ CORRECT: Let domain exceptions bubble up
@router.post("/workflows")
async def create_workflow(
    request: WorkflowCreate,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> Workflow:
    # No try-catch blocks for domain exceptions
    return await service.create_workflow(
        name=request.name,
        workflow_definition=request.workflow_definition,
    )
    # Domain exceptions automatically bubble to global handlers

# ❌ INCORRECT: Don't catch domain exceptions in routers
@router.post("/workflows")
async def create_workflow_wrong(
    request: WorkflowCreate,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> Workflow:
    try:
        return await service.create_workflow(name=request.name)
    except WorkflowNameConflictError as e:
        # DON'T DO THIS - breaks centralized error handling
        raise HTTPException(status_code=409, detail=str(e))
```

**Benefits:**
- Routers focus only on HTTP concerns (routing, validation, serialization)
- No duplicate error handling logic
- Automatic RFC 9457 compliance through global handlers

### Global Exception Handlers: RFC 9457 Conversion

**Global exception handlers convert domain exceptions to RFC 9457 compliant responses**:

```python
# Global handler registration in main.py
app.add_exception_handler(WorkflowNameConflictError, workflow_name_conflict_handler)
app.add_exception_handler(FileValidationError, file_validation_error_handler)
app.add_exception_handler(ToolNotFoundError, tool_not_found_handler)

# Handler implementation
async def workflow_name_conflict_handler(request: Request, exc: Exception) -> JSONResponse:
    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Workflow Name Conflict",
        detail="A workflow with this name already exists",  # Safe, generic message
        code="WORKFLOW_NAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )
```

**Benefits:**
- RFC 9457 compliance for all responses
- Centralized security controls (no sensitive data exposure)
- Consistent error response format
- Proper HTTP status code mapping

## Exception Categories and Status Codes

### Resource Not Found (404)
- `ToolNotFoundError`
- `ProviderNotFoundError`
- `WorkflowNotFoundError`
- `ExecutionNotFoundError`
- `WorkflowVersionNotFoundError`

### Validation Errors (400/422)
- `syntara.files.validators.ValidationError` → 400 (business logic validation)
- `syntara.tool_manager.lib.exceptions.ValidationError` → 422 (schema validation)
- `pydantic.ValidationError` → 422 (request validation)
- `fastapi.exceptions.RequestValidationError` → 422 (request validation)

### Conflict Errors (409)
- `WorkflowNameConflictError`
- `ProviderNameConflictError`

### Service Unavailable (503)
- `TemporalUnavailableError`
- `LLMConfigurationError`

### Generic Business Logic (400)
- `ProviderError`
- `ToolManagerError`

### System Errors (500)
- `RPCError` (Temporal)
- Generic `Exception` (catch-all)

## RFC 9457 Response Format

All error responses follow RFC 9457 Problem Details specification:

```json
{
  "type": "https://api.example.com/errors/name-conflict",
  "title": "Workflow Name Conflict",
  "detail": "A workflow with this name already exists",
  "code": "WORKFLOW_NAME_CONFLICT",
  "retryable": false,
  "instance": "/api/v1/workflows"
}
```

**Content-Type**: `application/problem+json`

## Security Considerations

### Information Disclosure Prevention

Global handlers implement security controls to prevent sensitive information leakage:

```python
async def workflow_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log full exception details for debugging
    logger.info("Workflow not found", exc_info=exc)

    # Return generic message (no workflow IDs, internal details)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="The requested workflow was not found",  # Generic, safe
        # Original exc.message might contain: "Workflow abc-123-def not found in database table workflows"
    )
```

### Safe Error Messages

- **Generic messages**: Avoid exposing internal implementation details
- **No sensitive data**: UUIDs, database details, file paths excluded from client responses  
- **Structured logging**: Full exception details logged for debugging, not exposed to clients

## Implementation Guidelines

### Adding New Domain Exceptions

#### Option 1: Recommended - Using @fastapi_exception Decorator

1. **Create domain exception with decorator** in appropriate domain module:
```python
from syntara.core.exception_registry import fastapi_exception

@fastapi_exception(handler=my_domain_error_handler)
class MyDomainError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
```

2. **Add global error handler**:
```python
async def my_domain_error_handler(request: Request, exc: MyDomainError) -> JSONResponse:
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,  # Choose appropriate status
        problem_type=PROBLEM_TYPES["validation_error"],
        title="My Domain Error",
        detail="Safe description of the error",
        code="MY_DOMAIN_ERROR",
        retryable=False,
        instance=str(request.url),
    )
```

3. **Import module to trigger registration** (if needed):
```python
# In main.py or wherever exceptions need to be registered
import my.domain.exceptions  # noqa: F401
```

4. **Automatic registration**: The decorator automatically registers the exception when `register_exceptions(app)` is called in `main.py`.

#### Option 2: Manual Registration (for 3rd-party exceptions)

For exceptions from third-party libraries that cannot be decorated:

1. **Add global error handler**:
```python
async def third_party_error_handler(request: Request, exc: ThirdPartyError) -> JSONResponse:
    return create_problem_details_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        problem_type=PROBLEM_TYPES["external_service_error"],
        title="External Service Error",
        detail="An external service encountered an error",
        code="EXTERNAL_SERVICE_ERROR",
        retryable=True,
        instance=str(request.url),
    )
```

2. **Register handler manually in main.py**:
```python
app.add_exception_handler(ThirdPartyError, third_party_error_handler)
```

**Note**: Use manual registration only when you cannot modify the exception class (e.g., exceptions from external libraries like `sqlalchemy.exc.IntegrityError`, `temporalio.service.RPCError`, etc.).

#### Service Usage

Use in services (not routers):
```python
class MyService:
    async def my_operation(self):
        if condition_fails:
            raise MyDomainError("Business logic explanation")
```

### Router Guidelines

- **HTTP concerns only**: Focus on request/response handling, routing, dependency injection
- **No exception catching**: Let domain exceptions bubble up naturally
- **HTTP validation only**: Catch `ValueError` for UUID parsing, `OSError` for immediate I/O failures
- **No `str(exc)` usage**: Avoid exposing exception messages directly

### Testing Considerations

When writing tests, expect the **correct HTTP status codes**:

```python
# ✅ CORRECT: Expect proper status codes
def test_duplicate_workflow_name():
    response = client.post("/workflows", json={"name": "existing"})
    assert response.status_code == 409  # Conflict, not 400

def test_validation_error():
    response = client.post("/workflows", json={"invalid": "data"})
    assert response.status_code == 422  # Unprocessable Entity, not 400

    # Expect RFC 9457 format
    data = response.json()
    assert "title" in data
    assert "detail" in data
    assert "type" in data
```

## Migration from Legacy Error Handling

If you encounter legacy router-level exception handling:

```python
# BEFORE (legacy pattern to remove):
try:
    result = await service.operation()
except DomainError as e:
    raise HTTPException(status_code=400, detail=str(e))

# AFTER (current pattern):
result = await service.operation()
# Let domain exceptions bubble up to global handlers
```

## Benefits of This Strategy

1. **Consistency**: All API consumers receive identical error response format
2. **Security**: Centralized control prevents information disclosure vulnerabilities
3. **Maintainability**: Single location for error response logic
4. **Standards Compliance**: RFC 9457 compliance across all endpoints
5. **Clean Architecture**: Clear separation between business logic and HTTP concerns
6. **Debugging**: Comprehensive error logging without exposing details to clients

## Conclusion

This centralized error handling strategy ensures that Syntara provides a professional, secure, and standards-compliant API experience. By maintaining the single exception boundary principle and letting domain exceptions bubble up to global handlers, we achieve consistent error responses while maintaining clean architectural boundaries.

All new code should follow this pattern, and any legacy error handling code should be migrated to use this centralized approach.
