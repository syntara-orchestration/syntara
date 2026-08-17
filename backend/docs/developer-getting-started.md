# Developer Getting Started Guide

Welcome to Syntara! This guide provides architectural deep-dives and practical examples to help you understand and work with our codebase patterns.

For setup instructions, see [README.md](../README.md).

## Understanding Base Resource Classes

All domain models should extend the `Resource` base class from `src/syntara/core/models/`. Here's the inheritance hierarchy:

```python
# Core hierarchy (from src/syntara/core/models/base/base_resource.py)
BaseResource (ABC)          # id, timestamps, labels
├─ NamedResource            # + name, description  
├─ SoftDeletableResource    # + deleted_at, deleted_by
├─ UserOwnedResource        # + created_by, updated_by
└─ Resource                 # Combines all above (recommended base)
```

**Note:** `Resource` uses multiple inheritance, inheriting from all three specialized base classes simultaneously.

**Complete example:**
```python
from syntara.core.models import Resource

class ToolProvider(Resource, table=True):
    """Extends Resource with provider-specific fields."""
    __tablename__ = "tool_providers"

    enabled: bool = Field(default=True)
    configuration: dict[str, Any] = Field(sa_type=JSONB)
    # All base fields inherited: id, name, description, timestamps, ownership, labels
```

### Available Base Classes

- **BaseResource**: Core fields (`id`, `created_at`, `updated_at`, `labels`)
- **NamedResource**: Adds `name` and `description` fields
- **SoftDeletableResource**: Adds `deleted_at` and `deleted_by` for soft deletion
- **UserOwnedResource**: Adds `created_by` and `updated_by` for ownership tracking
- **Resource**: Combines all above - use this for most domain models

## Router Discovery Framework

Syntara automatically discovers and registers FastAPI routers following specific conventions:

### File Locations
- `src/syntara/{domain}/router.py`
- `src/syntara/schemas/{domain}/openapi.yaml`

### Required Exports
Your router module must export one of:
- `router` variable (APIRouter instance)
- `build_router()` function  
- `build_{domain}_router()` function

### Example Router Structure
```python
from fastapi import APIRouter, Depends
from typing import Annotated

router = APIRouter(prefix="/tool-providers", tags=["tool-providers"])

# Dependency injection pattern
def get_tool_provider_service(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ToolProviderService:
    return ToolProviderService(db, current_user)

# Route handlers delegate to services
@router.get("/")
async def list_providers(
    service: Annotated[ToolProviderService, Depends(get_tool_provider_service)]
) -> list[ToolProvider]:
    return await service.list_providers()
```

The discovery system (`src/syntara/core/router_discovery.py`) automatically scans these locations and registers all routers with the FastAPI app.

## Tool Manager Example - Complete Pattern

`src/syntara/tool_manager/` demonstrates the full Syntara architecture pattern:

### 1. Models (`tool_manager/models/`)

**ToolProvider Model:**
```python
class ToolProvider(Resource, table=True):
    __tablename__ = "tool_providers"

    enabled: bool = Field(default=True)
    configuration: dict[str, Any] = Field(sa_type=JSONB)

    # Filterable/sortable fields for API
    __filterable_fields__ = ["enabled", "name", "created_at"]
    __sortable_fields__ = ["name", "created_at", "updated_at"]
```

**Tool Model with Relations:**
```python
class Tool(Resource, table=True):
    __tablename__ = "tools"

    provider_id: UUID = Field(foreign_key="tool_providers.id")
    tool_type: str
    parameters: dict[str, Any] = Field(sa_type=JSONB)

    # Relationship
    provider: ToolProvider = Relationship(back_populates="tools")
```

### 2. Services (`tool_manager/services/`)

**Service Layer Pattern:**
```python
class ToolProviderService:
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user

    async def create_provider(self, data: ToolProviderCreate) -> ToolProvider:
        # Business logic here
        provider = ToolProvider(**data.model_dump(), created_by=self.current_user.id)

        try:
            self.db.add(provider)
            await self.db.commit()
            await self.db.refresh(provider)
            return provider
        except IntegrityError as e:
            await self.db.rollback()
            if "unique_constraint" in str(e):
                raise ProviderNameConflictError(f"Provider '{data.name}' already exists")
            raise
```

### 3. Error Handling (`tool_manager/lib/exceptions.py`)

**Domain-Specific Exceptions:**
```python
class ToolManagerError(Exception):
    """Base exception for tool manager domain."""

class ProviderNameConflictError(ToolManagerError):
    """Raised when a provider name already exists."""

class ProviderNotFoundError(ToolManagerError):
    """Raised when a provider cannot be found."""
```

**Router — Let Exceptions Bubble Up:**

Routers do NOT catch domain exceptions. They bubble up to global exception handlers that produce RFC 9457 compliant responses. See [Error Handling Strategy](error-handling-strategy.md) for details.

```python
@router.post("/")
async def create_provider(
    data: ToolProviderCreate,
    service: Annotated[ToolProviderService, Depends(get_tool_provider_service)]
) -> ToolProvider:
    # No try-catch — domain exceptions bubble to global handlers
    return await service.create_provider(data)
```

## OpenAPI Schema Integration

Syntara uses a structured approach to OpenAPI documentation:

### Shared Resources (`src/syntara/schemas/base/shared-resources.openapi.yaml`)
```yaml
components:
  schemas:
    Resource:
      type: object
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
        description:
          type: string
        createdAt:
          type: string
          format: date-time
        # ... other base fields
```

### Domain Schemas (`src/syntara/schemas/tool_manager/openapi.yaml`)
```yaml
components:
  schemas:
    ToolProvider:
      allOf:
        - $ref: ../base/shared-resources.openapi.yaml#/components/schemas/Resource
        - type: object
          properties:
            enabled:
              type: boolean
            configuration:
              type: object
```

## Database Migration Patterns

### 1. Model Changes First
```python
# Update your SQLModel class
class ToolProvider(Resource, table=True):
    __tablename__ = "tool_providers"

    enabled: bool = Field(default=True)
    max_concurrent_jobs: int = Field(default=5)  # New field
    configuration: dict[str, Any] = Field(sa_type=JSONB)
```

### 2. Generate Migration
```bash
uv run alembic revision --autogenerate -m "Add max_concurrent_jobs to tool_providers"
```

## Development Patterns

### 1. Service Layer Best Practices
- Keep routers thin - delegate all business logic to services
- Use dependency injection for clean separation
- Services handle validation, database operations, and domain logic
- Domain exceptions bubble up to global handlers (do NOT catch in routers)

### 2. Error Handling Strategy
- Create domain-specific exception classes
- Raise meaningful exceptions in service layer
- Global exception handlers convert to RFC 9457 responses with appropriate HTTP status codes
- Routers focus on HTTP concerns only (routing, validation, serialization)
- See [Error Handling Strategy](error-handling-strategy.md) for the full pattern

### 3. Testing Strategy
```python
# Unit tests for services
async def test_create_provider_duplicate_name():
    with pytest.raises(ProviderNameConflictError):
        await service.create_provider(ToolProviderCreate(name="existing"))

# Integration tests for database operations
async def test_provider_crud_operations(db_session):
    provider = await service.create_provider(sample_data)
    assert provider.id is not None
    assert provider.name == sample_data.name
```

## Next Steps

1. **Examine existing implementations:**
   - Study `src/syntara/tool_manager/` for the complete pattern
   - Review `src/syntara/core/models/` for base class usage

2. **Try a small change:**
   - Add a field to an existing model
   - Generate and apply a migration
   - Update the corresponding service and router

3. **Build a new domain:**
   - Follow the domain structure pattern in `src/syntara/{domain}/`
   - Extend `Resource` for your models
   - Implement services with proper error handling
   - Create router with dependency injection
