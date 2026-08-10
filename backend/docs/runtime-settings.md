# Runtime Settings

## Overview

Runtime settings are database-backed configuration values that can be changed without redeploying the application. Settings are stored in PostgreSQL and accessible to other backend code via `SettingsCache`, and manageable by administrators through the REST API and Settings UI page.

Like `syntara.core.config`, Runtime settings are accessed by a short key, have default values, and enforce validation criteria.

Unlike `syntara.core.config`, Runtime settings are not configurable by environment variables. They are user-controlled and should not be used for install-time configuration settings that require deployment changes (such as database connection details or HTTP server configuration). Those configuration settings should remain in `syntara.core.config` and configurable by environment variable.

Since Runtime settings may be written by multiple clients, they employ a version number to guarantee consistency using optimistic locking.

Key design points:

- **No migration needed for new settings** -- add a `SettingDefinition` to the catalog and run the post-migration seeder
- **JSONB storage** -- values are stored as native Python types, not strings
- **Optimistic locking** -- concurrent writes are safe; version conflicts are detected
- **Two-tier caching** -- L1 in-process dict (zero-latency) plus optional L2 Redis cache (shared across processes), with TTL-based expiry and stale-value fallback
- **Change notification** -- Redis Pub/Sub for near-real-time propagation, with polling fallback when Redis is unavailable
- **Change watchers** -- register a callback with `@watch_setting` to react when a setting value changes at runtime

## Reading Settings

Access settings through the `SettingsCache` singleton via `get_runtime_settings()`. All reads are `async`:

```python
from syntara.settings.cache.settings_cache import get_runtime_settings

class MyService:
    def __init__(self) -> None:
        self.settings = get_runtime_settings()

    async def do_work(self) -> None:
        temperature = await self.settings.get_float("context_manager.compression_temperature")
        max_tokens = await self.settings.get_int("context_manager.max_total_tokens")
```

The cache resolves the effective value: user-set `value` if present, otherwise `default_value`. Values are cached with a TTL (default 60 seconds) at two tiers:

1. **L1 (in-process dict)** -- zero-latency, per-process
2. **L2 (Redis)** -- shared across processes, optional

On a read, L1 is checked first. On L1 miss, L2 is checked. On L2 miss, the database is queried and the result is stored in both L1 and L2. Settings with `requires_restart=True` are cached for the lifetime of the process. If the database is temporarily unreachable, stale L1 cached values are returned rather than raising an error.

### Typed getter methods

Use the typed getter methods to ensure values are validated at read time:

| Method       | Returns | Notes                                                    |
|--------------|---------|----------------------------------------------------------|
| `get_int()`  | `int`   | Rejects `bool` values                                   |
| `get_float()`| `float` | Accepts `int` (coerces to `float`); rejects `bool`      |
| `get_str()`  | `str`   |                                                          |
| `get_bool()` | `bool`  |                                                          |
| `get()`      | `Any`   | Untyped; use for JSON-type settings or when type is mixed|

Each typed method accepts an optional `default` keyword argument. If the setting is missing or `None` and no default is provided, a `SettingTypeError` is raised. If the stored value has the wrong type, a `SettingTypeError` is also raised.

```python
# With a fallback default
timeout = await self.settings.get_int("context_manager.request_timeout_seconds", default=30)

# For JSON-type settings, use the untyped get()
priority_order = await self.settings.get("context_manager.priority_order")
```

> **Important**: Always access settings through `get_runtime_settings()`. Using `SettingsCache` ensures your code benefits from two-tier caching and change notification automatically.

## Defining a New Setting

Add a `SettingDefinition` entry to `SETTINGS_CATALOG` in `src/syntara/settings/catalog.py`:

```python
from syntara.settings.catalog import SettingDefinition
from syntara.settings.models.runtime_setting import SettingCategory, SettingValueType

SettingDefinition(
    key="system.max_retries",                  # dot-namespaced key
    name="Max retries",                        # human-readable name
    category=SettingCategory.SYSTEM,           # UI tab grouping
    value_type=SettingValueType.INTEGER,       # string | integer | float | boolean | json
    default_value=3,                           # native Python type, not a string
    description="Maximum retry attempts for my feature.",
    group="Reliability",                       # UI section heading within the tab
    requires_restart=False,                    # True if change needs app restart
    cache_ttl_seconds=None,                    # None = use default (60s)
    validation_schema={"min": 0, "max": 10},  # optional constraints
)
```

That's it. After running migrations and the seeder, the definition is upserted into the `runtime_settings` table:

```bash
uv run alembic upgrade head
uv run python -m syntara.seed --only settings
```

If no row matching the setting exists, a row will be inserted. If a row does exist, the user-controlled `value` and `version` will be preserved but the other metadata fields (including `default_value`) will be updated. The seeder does not run at app startup — it runs as a post-migration step.

### Key conventions

- Use dot-namespaced keys: `category.setting_name`
- Use an existing category slug from `CATEGORY_CATALOG`, or add a new one (see [Adding a New Category](#adding-a-new-category)).
- `default_value` must be a native Python type matching `value_type`

### Validation schema

The optional `validation_schema` dict supports these constraints:

| Key              | Applies to     | Example                                 |
| ---------------- | -------------- | --------------------------------------- |
| `min`            | integer, float | `{"min": 0}`                            |
| `max`            | integer, float | `{"max": 100}`                          |
| `allowed_values` | string         | `{"allowed_values": ["DEBUG", "INFO"]}` |
| `pattern`        | string         | `{"pattern": "^[a-z]+$"}`               |

Validation runs on every write through the REST API.

## REST API

Settings are managed via the REST API at `/api/v1/settings`. All endpoints require the ADMINISTRATOR role.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/settings` | List all settings (paginated, filterable by category/group) |
| `GET` | `/settings/categories` | List all categories with group names |
| `GET` | `/settings/{key}` | Get a single setting by dot-namespaced key |
| `PATCH` | `/settings/{key}` | Update a setting value |
| `PATCH` | `/settings` | Bulk update multiple settings |

### Updating a setting

Optionally include `expected_version` for optimistic locking. When omitted, the update applies unconditionally. The Settings UI always sends `expected_version` to detect concurrent edits:

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/context_manager.max_total_tokens \
  -H "Content-Type: application/json" \
  -d '{"value": 8000, "expected_version": 1}'
```

### Resetting to default

To reset a setting, set `value` to the setting's `default_value`:

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/context_manager.max_total_tokens \
  -H "Content-Type: application/json" \
  -d '{"value": 4000, "expected_version": 2}'
```

> **Note:** User-specified values cannot be `null`. Internally, `null` means "use the default value" and is managed by the seeder. The API rejects `null` values with a 422 error.

### Bulk operations

Update multiple settings at once:

```bash
curl -X PATCH http://localhost:8000/api/v1/settings \
  -H "Content-Type: application/json" \
  -d '{"updates": [
    {"key": "context_manager.max_total_tokens", "value": 8000, "expected_version": 1},
    {"key": "context_manager.max_context_tokens", "value": 4000, "expected_version": 1}
  ]}'
```

### Filtering and pagination

The list endpoint supports cursor-based pagination and filtering:

```bash
# Filter by category
curl -s "http://localhost:8000/api/v1/settings?category=context_manager"

# Filter by group
curl -s "http://localhost:8000/api/v1/settings?group=Token+limits"

# Pagination (limit, cursor, sort)
curl -s "http://localhost:8000/api/v1/settings?limit=10&sort=key"
```

### Limits

- **Bulk operations**: Maximum 500 items per request
- **Value size**: Maximum 64KB per setting value (serialized JSON)
- **Pagination**: Maximum 100 items per page (default 20)

### Error responses

All errors follow [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) Problem Details format:

| Status | Code | When |
|--------|------|------|
| `403` | — | User is not an administrator |
| `404` | `SETTING_NOT_FOUND` | Unknown key |
| `409` | `SETTING_VERSION_CONFLICT` | Optimistic lock version mismatch |
| `422` | `SETTING_VALIDATION_ERROR` | Value fails type or constraint checks |

## Change Notification

When a setting is updated via the REST API, the change is propagated to all processes through two complementary mechanisms:

1. **Redis Pub/Sub** (near-real-time) -- the `SettingsService` publishes a message on the `syntara:settings:changes` channel after each successful update. A subscriber task in `SettingsCache` receives the message and updates the L1 cache and fires any registered `@watch_setting` callbacks.
2. **Polling** (fallback) -- a `PeriodicWorker` polls the database for watched keys at the cache TTL interval. This always runs alongside Pub/Sub and serves as the sole notification mechanism when Redis is unavailable.

### Graceful degradation

Redis is optional. If Redis is unavailable at startup, the cache operates with L1 + DB only and polling-based change detection. If Redis becomes available later, the cache lazily acquires a connection and starts Pub/Sub. If Redis goes down after initial connection, the cache falls back to polling and automatically reconnects when Redis recovers.

## Watching for Changes

Most settings are read on demand via `get_runtime_settings()` and don't need any special handling when they change -- the next read will pick up the new value after the cache TTL expires.

Some settings, however, require an immediate action when their value changes. For example, changing the log level needs to reconfigure the Python logging subsystem. For these cases, use the `@watch_setting` decorator to register a change handler:

```python
from syntara.settings.watch import watch_setting

@watch_setting("logging.log_level")
def _on_log_level_changed(_key: str, new_value: Any) -> None:
    level = str(new_value).upper()
    _set_log_level(level)
```

The application lifecycle handles the rest -- no additional wiring is needed. The decorated function will be called with `(key, new_value)` whenever a change is detected via Pub/Sub or the polling fallback.

### When to use a watcher

- The setting controls something that must be actively reconfigured (log levels, connection pool sizes, feature flags that gate background workers)
- A simple "read the latest value next time" is not sufficient

### When you don't need a watcher

- The setting is read on each request or operation (e.g. token limits, thresholds). The TTL-based cache already ensures reads pick up changes within the polling interval.

### Requirements

- Only settings with `requires_restart=False` can be watched. Attempting to watch a `requires_restart=True` setting raises `ValueError`.
- The module containing the decorated function must be imported during normal application startup (i.e. part of the regular import chain).
- Handlers can be sync or async. Async handlers are awaited.
- **Handlers must return quickly.** Callbacks run sequentially -- a slow or blocking handler will delay change detection for all other watched settings. Keep handlers limited to fast, in-process operations (e.g. reconfiguring a logger, updating a module-level variable). Do not make network requests or database calls from a watcher callback.

## Migrating from `syntara.core.config`

### Pattern 1: Cache read (most settings)

The standard pattern. Consumers read live values from the settings cache at the point of use. No watchers, no startup functions, no module-level state.

**Steps:**

1. **Add the `SettingDefinition`** to `SETTINGS_CATALOG` with the correct default value and validation schema
2. **Remove the Pydantic field** from `base.py` -- the catalog is now the single source of truth
3. **Read from the cache** at the point of use:

```python
cache = get_runtime_settings()
timeout = await cache.get_int("document_conversion.timeout_seconds")
```

The cache resolves the effective value (user-set or catalog default) and handles caching via TTL. Changes made in the Settings UI propagate automatically.

**Implementation details:**

- **Pydantic Field defaults.** Some settings are used as Pydantic `Field(default=...)` values (e.g., `ScriptExecutorConfig.timeout`). These defaults are evaluated at class definition time and use a hardcoded literal. The activity injects the live value from the cache before calling `model_validate()`:

  ```python
  # In the activity, before validation:
  if "timeout" not in input_config:
      cache = get_runtime_settings()
      input_config["timeout"] = await cache.get_int("workflow_engine.script_timeout_seconds")
  config = ScriptExecutorConfig.model_validate(input_config)
  ```

- **Temporal workflow sandbox.** Workflow code (`@workflow.defn`) cannot do async cache reads. Omit the value from the workflow state and let the activity resolve it from the cache:

  ```python
  # In the workflow (sandbox) -- do NOT pass a default:
  loop_state = {"type": "do_while", "current_index": 0}
  if "max_iterations" in resolved_config:
      loop_state["max_iterations"] = resolved_config["max_iterations"]
  # If omitted, the loop activity reads it from the settings cache.
  ```

- **`requires_restart=True` settings.** For settings like `retriever.llm_model` that cannot change at runtime, the Pydantic field stays as-is. No cache read, no watcher -- changes only take effect on restart.

### Pattern 2: Watcher (settings requiring immediate side effects)

Use this only when a setting change must trigger an immediate action in the process -- not just return a new value on the next read, but actively reconfigure something. The only current example is `logging.log_level`, which must reconfigure Python's logging subsystem.

**Steps:**

1. **Add the `SettingDefinition`** to `SETTINGS_CATALOG`
2. **Create a `runtime_settings.py` module** with an `apply_runtime_*()` startup function and `@watch_setting` handlers
3. **Wire the apply function** into `main.py` and `worker.py` startup

```python
@watch_setting("logging.log_level")
def _on_log_level_changed(_key: str, new_value: Any) -> None:
    level = str(new_value).upper()
    _set_log_level(level)
```

Most settings do **not** need this pattern. If the consumer reads the value on each request or activity execution, Pattern 1 is sufficient and simpler.

## Architecture

```text
SETTINGS_CATALOG (Python)
        |
        v
    Seeder (post-migration)  ──upsert──>  runtime_settings (PostgreSQL)
                                                  ^
                                                  |
                                    ┌─────────────┴─────────────┐
                                    |                           |
                          SettingsStore              SettingsService (BaseService)
                       (read-only data access)              |
                                    ^                       |── invalidate + publish_change
                                    |                       |
                          SettingsCache              REST API
                          (L1 + L2 cache)         (/api/v1/settings)
                                |
                    ┌───────────┼───────────┐
                    |           |           |
               L1 (dict)   L2 (Redis)   Redis Pub/Sub
              per-process    shared     syntara:settings:changes
                    |                      |
                    |              ┌───────┴───────┐
                    |              |               |
                    |        Pub/Sub listener  Polling worker
                    |              |           (DB fallback)
                    |              └───────┬───────┘
                    |                      |
                    |                      v
                    |              @watch_setting callbacks
                    |
          get_runtime_settings() singleton
                    ^
                    |
          Application code reads
```

## Adding a New Category

Categories are stored in the `setting_categories` database table and seeded
from `CATEGORY_CATALOG` in `src/syntara/settings/catalog.py`. To add a new
category:

1. Add a `CategoryDefinition` entry to `CATEGORY_CATALOG` with a unique slug,
   display name, description, and display order.
2. Add the slug to the `SettingCategory` enum in
   `src/syntara/settings/models/runtime_setting.py` (used for type-safe
   references in `SETTINGS_CATALOG`).
3. Run the seeder (`make dev` or `uv run python -m syntara.seed --only settings`) —
   no migration is needed.
