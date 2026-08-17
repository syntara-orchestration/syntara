# Database Standards

This document defines database patterns for the Syntara project. PostgreSQL is the primary data store; Redis is used only for ephemeral caching (see [Redis](redis.md)).

## Connection Management

### Engine Configuration

Database connections are managed via SQLAlchemy async engine in `src/syntara/core/database/session.py`:

```python
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=settings.db_pool_size,        # Default: 10 persistent connections
    max_overflow=settings.db_max_overflow,   # Default: 20 extra temporary connections
    pool_timeout=settings.db_pool_timeout_seconds,  # Default: 30s wait for connection
    pool_pre_ping=True,                     # Verify connection before use
    pool_recycle=3600,                      # Recycle after 1 hour (prevents stale connections)
)
```

All pool parameters except `pool_pre_ping` and `pool_recycle` are configurable via `DatabaseSettings` in `src/syntara/core/config/base.py`.

### PostgreSQL Server `max_connections`

The default PostgreSQL `max_connections=100` is insufficient for production deployments. Each backend or worker replica can open up to `pool_size + max_overflow` connections (default: 30), and the Temporal server maintains its own connection pool (~30 connections). The total across all replicas exceeds 100 at moderate scale.

Recommended minimums based on connection budget analysis:

| Deployment size | Temporal Server | Workers | Backend replicas | Estimated total PG connections | Recommended `max_connections` |
|-----------------|-----------------|---------|------------------|-------------------------------|-------------------------------|
| Default (1/2/2) | 1 | 2 | 2 | 75–115 | 200 |
| Large (1/4/2) | 1 | 4 | 2 | 95–155 | 300 |

Set `max_connections` with headroom above the estimated total to account for maintenance connections and monitoring tools. The memory overhead is ~5–10 MB per connection slot.

### Session Lifecycle

Use the `get_db()` dependency for **all** database access in endpoints and services:

```python
@router.get("/resources")
async def list_resources(db: Annotated[AsyncSession, Depends(get_db)]):
    ...
```

`get_db()` provides automatic transaction management:
- Commits on success
- Rolls back on exception
- Closes session in `finally`

**Do NOT use `AsyncSessionLocal` directly.** Direct usage bypasses FastAPI's `dependency_overrides`, which means code will always connect to the production database configuration — even in tests where `dependency_overrides` has been set to use a test database. This breaks test isolation: test setup writes to the test database via `get_db()`, but any code path using `AsyncSessionLocal` reads from/writes to the production database. Always obtain sessions through `get_db()` and FastAPI's dependency injection.

### Session Factory for Testing

`src/syntara/core/utils/session_factory.py` provides `create_session_factory_from_request()` which respects FastAPI's `dependency_overrides`. This allows tests to substitute a test database session without modifying endpoint code.

### Single-Database Architecture

Syntara uses a **single PostgreSQL database** for all application data, including the audit outbox. Audit events are written to the outbox table in the main database and asynchronously exported to the OTEL collector by the `AuditOutboxWorker`.

- Use `get_db()` for all database access (domain models, audit outbox, etc.)
- Schema is managed via a single Alembic migration tree in `src/syntara/core/database/migrations/`

## Migrations

### Baseline

Schema history was flattened into a single baseline revision (`b69ef9067e66`). There is
**no in-place upgrade path** from databases created with the previous revision chain.

After pulling this change, wipe and recreate local or long-lived databases, then migrate
and seed:

```bash
# From repo root — destroy the Postgres volume and bring the stack back up
podman compose -f podman-compose.yml down -v
# then start services as usual (e.g. make run-all from backend/)
# syntara startup runs: alembic upgrade head && python -m syntara.seed --all
```

For a database outside Compose, if it is a dedicated local/dev AO database
created from the previous migration chain, start with a fresh database before
migrating and seeding. There is no in-place upgrade path from the previous
migration history.

```bash
uv run alembic upgrade head
uv run python -m syntara.seed --all
```

### Alembic Workflow

All schema changes MUST go through Alembic migrations. Models are the source of truth — update models first, then generate migrations:

```bash
uv run alembic revision --autogenerate -m "description of change"
```

### Migration Naming

Migrations use random hexadecimal prefixes (e.g., `2314ee1fbabf_add_approval_requests_table.py`) instead of sequential numbering. This prevents merge conflicts when multiple branches create migrations simultaneously.

### Model Registration

All models must be imported in `src/syntara/core/database/migrations/env.py` to register with SQLModel's metadata. If a model isn't imported there, Alembic won't detect its schema changes.

### Custom SQL in Migrations

When autogenerated code is insufficient:

- Place custom code outside the `# ### commands auto generated by Alembic` blocks
- Mark with `# CUSTOM: <reason>` and `# END CUSTOM`
- Document the reason in the migration docstring

### CI Validation

`make check-migrations` validates the migration sequence in CI. Run it before pushing migration changes.

## Label Filtering

### Storage

Labels are stored as PostgreSQL JSONB on all `BaseResource` subclasses. The column has a server default of `'{}'::jsonb`.

### GIN Index

Resources that support label filtering MUST define a GIN (Generalized Inverted Index) for performance:

```python
class Workflow(Resource, table=True):
    __table_args__ = (
        Index("ix_workflows_labels", "labels", postgresql_using="gin"),
    )
```

GIN indexes optimize the `@>` (contains) and `has_key` operators used by label queries.

### Query Operators

Label filtering in `BaseService` uses two PostgreSQL operators:

| API syntax | PostgreSQL operator | Purpose |
|---|---|---|
| `?labels[env]=prod` | `@>` (contains via `.contains()`) | Match key-value pair |
| `?labels[env]=` | `has_key()` | Check key exists (any value) |

Implementation in `src/syntara/core/utils/labels.py` and `src/syntara/core/services/base.py`.

## Soft Delete Filtering

Soft-deleted records are excluded from queries by filtering `WHERE deleted_at IS NULL`. This is applied explicitly in service methods — there is no automatic event-based filtering because `do_orm_execute` is not available for `AsyncSession`.

## Tooling vs Convention

**Enforced by tooling:**

- Alembic validates migration sequence (`make check-migrations`)
- Pydantic validates `DatabaseSettings` field types and constraints at startup
- `pool_pre_ping` verifies connections before use (prevents stale connection errors)
- GIN index defined in model `__table_args__` is created by Alembic migration

**Convention only:**

- Using `get_db()` dependency for all database access (not enforced)
- Model registration in `env.py` (missing models silently won't generate migrations)
- GIN index creation for label-filterable models
- Custom SQL marking convention (`# CUSTOM:` / `# END CUSTOM`)
- Migration naming (random prefix handled by Alembic automatically)

## Reference

| File | Purpose |
|---|---|
| `src/syntara/core/database/session.py` | Engine, session factory, `get_db()` |
| `src/syntara/core/config/base.py` | `DatabaseSettings` (pool configuration) |
| `src/syntara/core/database/migrations/env.py` | Alembic migration environment |
| `src/syntara/core/database/migrations/versions/` | Migration files |
| `src/syntara/core/utils/session_factory.py` | Test-compatible session factory |
| `src/syntara/core/utils/labels.py` | Label filter JSONB operations |
| `src/syntara/core/services/base.py` | Label filter application in queries |
