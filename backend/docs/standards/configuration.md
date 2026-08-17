# Configuration Standards

This document defines the configuration patterns for the Syntara project. All application settings use Pydantic Settings v2 with environment variable injection.

## Architecture

Configuration uses a multi-inheritance architecture where the main `Settings` class inherits from domain-specific `BaseSettings` subclasses:

```python
class Settings(
    OpenRouterSettings,
    DatabaseSettings,
    CacheSettings,
    ServerSettings,
    LoggingSettings,
    TemporalSettings,
    # ... other domain settings
):
    model_config = SettingsConfigDict(
        env_file=_get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="APP_",
    )
```

**Key properties:**

- All environment variables use the `APP_` prefix
- Case-insensitive matching (`APP_DB_HOST` and `app_db_host` both work)
- Extra environment variables are ignored (no validation errors for unrecognized vars)
- Optional `.env` file support (path configurable via `APP_ENV_FILE_PATH`)

## Settings Singleton

Settings are accessed via a cached singleton:

```python
from syntara.core.config.base import get_settings

settings = get_settings()
model = settings.openrouter_model
```

The `get_settings()` function uses `@lru_cache` to avoid repeated `.env` file reads. Domain settings classes should not be instantiated directly.

## Environment Variable Naming

| Python field | Environment variable |
|---|---|
| `db_host` | `APP_DB_HOST` |
| `openrouter_model` | `APP_OPENROUTER_MODEL` |
| `cache_port` | `APP_CACHE_PORT` |

**Convention:** Field names use `lowercase_with_underscores`. The `APP_` prefix is added automatically by Pydantic.

## Field Definition Patterns

### Basic Fields

```python
class MyFeatureSettings(BaseSettings):
    """MyFeature configuration settings.

    Note: This class should not be instantiated directly.
    Use Settings via get_settings().
    """

    feature_enabled: bool = Field(
        default=False,
        description="Enable the feature",
    )

    feature_timeout_seconds: int = Field(
        default=30,
        description="Timeout for feature operations",
        ge=1,
    )
```

### Secret Values

Use `SecretStr` for sensitive values to prevent accidental logging:

```python
from pydantic import SecretStr

class CacheSettings(BaseSettings):
    cache_password: SecretStr = Field(
        description="Cache server password — set via APP_CACHE_PASSWORD",
    )
```

Access the value explicitly:

```python
password = settings.cache_password.get_secret_value()
```

### Sensitive Settings with Path-Based Loading

For encryption keys and other high-value secrets, support loading from a file path as well as a direct env var. The file path takes precedence when both are set.

```python
class CredentialEncryptionSettings(BaseSettings):
    secret_encryption_key: SecretStr = Field(
        description="64-character hex string (32 bytes) for AES-256-GCM encryption.",
    )

    secret_encryption_key_path: str | None = Field(
        default=None,
        description="Path to a file containing the hex key. Takes precedence over direct value.",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_encryption_key_from_path(cls, data: dict[str, Any]) -> dict[str, Any]:
        path = data.get("secret_encryption_key_path")
        if path is None:
            return data
        key_file = Path(path)
        if not key_file.is_file():
            raise SafeValueError(f"... file does not exist: {path}")
        data["secret_encryption_key"] = key_file.read_text().strip()
        return data
```

**Rules for sensitive settings:**

- **No insecure defaults.** Encryption keys, signing keys, and auth tokens must be required fields with no default value. A startup failure is better than silent insecurity.
- **Reject known-bad values.** Validators must explicitly reject placeholder values (e.g., all-zeros keys) with an error message that includes generation instructions.
- **Support `_PATH` suffix.** Follow the existing pattern: `APP_SECRET_ENCRYPTION_KEY_PATH`, `APP_JWT_PRIVATE_KEY_PATH`, `APP_ADMIN_PASSWORD_PATH`. File-based loading avoids exposing secrets in process listings and environment dumps.
- **Defense-in-depth.** The consuming function (e.g., `key_from_string()`) should also reject insecure values, even though the validator already prevents them.

Generate keys for local development:

```bash
# Generates .secrets/encryption-key, JWT keys, admin password
make secrets-generate

# Or manually:
openssl rand -hex 32
python -c "import secrets; print(secrets.token_hex(32))"
```

### Computed Fields

Use `@computed_field` for values derived from other settings:

```python
from sqlalchemy.engine import URL

@computed_field  # type: ignore[prop-decorator]
@property
def database_url(self) -> URL:
    """Build database URL from components using URL.create().

    Returns a SQLAlchemy URL object which keeps credentials out of
    string representations, preventing accidental exposure in logs
    or error messages.
    """
    return URL.create(
        drivername="postgresql+asyncpg",
        username=self.db_user,
        password=self.db_password.get_secret_value(),
        host=self.db_host,
        port=self.db_port,
        database=self.db_name,
    )
```

`URL.create()` is preferred over string interpolation because SQLAlchemy's `URL` object redacts the password in its `__repr__` and `__str__` representations. If `APP_DATABASE_URL` override is needed, handle it separately via an environment variable check before calling `create_async_engine`.

### Cross-Field Validation

Use `@model_validator` for constraints across multiple fields:

```python
@model_validator(mode="after")
def validate_backoff_relationship(self) -> Self:
    """Validate that max_backoff >= initial_backoff."""
    if self.adapter_max_backoff_seconds < self.adapter_initial_backoff_seconds:
        msg = (
            f"adapter_max_backoff_seconds ({self.adapter_max_backoff_seconds}) "
            f"must be >= adapter_initial_backoff_seconds "
            f"({self.adapter_initial_backoff_seconds})"
        )
        raise SafeValueError(msg)
    return self
```

### Default Factories

Use `default_factory` for computed defaults:

```python
storage_dir: str = Field(
    default_factory=tempfile.gettempdir,
    description="Storage directory for uploads",
)
```

## Adding a New Setting

### Step 1: Create a Domain Settings Class

Create a new `BaseSettings` subclass in `src/syntara/core/config/base.py`:

```python
class MustGatherSettings(BaseSettings):
    """Must-gather operation configuration.

    Note: This class should not be instantiated directly.
    Use Settings via get_settings().
    """

    must_gather_namespace: str = Field(
        default="openshift-must-gather-operator",
        description="Kubernetes namespace for must-gather operations",
    )

    must_gather_service_account: str = Field(
        default="must-gather-admin",
        description="Default service account for must-gather jobs",
    )
```

### Step 2: Add to Settings Inheritance

```python
class Settings(
    # ... existing classes ...
    MustGatherSettings,
):
```

### Step 3: Add to `.env.example`

```bash
# Must-Gather Configuration
APP_MUST_GATHER_NAMESPACE=openshift-must-gather-operator
APP_MUST_GATHER_SERVICE_ACCOUNT=must-gather-admin
```

### Step 4: Write Tests

See the Testing section below.

## Field Naming Conventions

- Include units of measure: `timeout_seconds`, `max_size_mb`, `polling_interval_seconds`
- Use descriptive prefixes matching the domain: `cache_host`, `db_port`, `openrouter_model`
- Boolean fields: use positive names (`feature_enabled`, not `feature_disabled`)
- Numeric constraints: always specify `ge`, `le`, `gt`, or `lt` where applicable

## Testing Configuration

### Override Settings in Tests

Use the `override_settings` fixture:

```python
def test_something(override_settings):
    with override_settings(
        openrouter_model="test/model",
        server_port=9000,
    ):
        settings = get_settings()
        assert settings.server_port == 9000
```

### Direct Environment Variable Override

```python
def test_database_settings(monkeypatch):
    monkeypatch.setenv("APP_DB_USER", "testuser")
    monkeypatch.setenv("APP_DB_PASSWORD", "testpass")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.db_user == "testuser"
```

### Validation Tests

```python
def test_timeout_must_be_positive(monkeypatch):
    monkeypatch.setenv("APP_FEATURE_TIMEOUT_SECONDS", "0")

    get_settings.cache_clear()
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        get_settings()
```

## Constants Module

All magic numbers and validation limits are centralized in `src/syntara/core/constants.py`. No hardcoded numeric literals in application code.

**Classes:**

| Class | Purpose | Examples |
|---|---|---|
| `FieldLimits` | String length limits, pagination bounds | `NAME_MAX_LENGTH=255`, `MAX_ITEMS_PER_PAGE=100`, `MAX_CURSOR_SIZE=1024` |
| `WebSocketConfig` | Connection and health check settings | `MAX_MESSAGE_SIZE=1MB`, `MAX_CONNECTIONS=100`, `CLEANUP_INTERVAL=30s`, `ACTIVITY_TIMEOUT=4h` |
| `ValidationMessages` | Reusable error message templates | `LABELS_MUST_BE_DICT`, `CURSOR_TOO_LARGE` |
| `RetrieverServiceDefaults` | LLM and keyword search defaults | Model names, thresholds, ranking weights (must sum to 1.0) |

**Usage:**

```python
from syntara.core.constants import FieldLimits, ValidationMessages

name: str = Field(max_length=FieldLimits.NAME_MAX_LENGTH)
```

**When adding constants:**

1. Add to the appropriate class in `constants.py`
2. Use the constant in code — never hardcode the value
3. If no existing class fits, create a new class with a descriptive name

## Tooling vs Convention

**Enforced by tooling:**

- Pydantic validates types, constraints, and cross-field rules at runtime
- Missing required fields (no default) raise `ValidationError` on startup
- `SecretStr` prevents accidental logging of secrets

**Convention only:**

- Domain settings class naming (`{Domain}Settings`)
- Field naming conventions (units of measure, descriptive prefixes)
- `.env.example` kept in sync with code
- Domain settings docstrings documenting purpose
- Constants centralized in `constants.py` (no tooling enforcement)

## Runtime Settings (Global Settings Framework)

The Global Settings Framework (GSF) provides **database-backed runtime settings** that can be modified without restarting the application. This is distinct from the environment-based `Settings` class documented above.

**When to use which:**

| System | Use case | Changed by | Takes effect |
|---|---|---|---|
| `get_settings()` (this document) | Infrastructure config: database URLs, ports, API keys, pool sizes | Environment variables / `.env` | Application restart |
| Runtime Settings (GSF) | Application behavior: LLM parameters, feature toggles, thresholds | REST API / UI | Immediately |

**Key components:**

- `RuntimeSetting` model in `src/syntara/settings/models/` — DB-backed with JSONB value storage
- Settings catalog in `src/syntara/settings/catalog.py` — declarative registry of settings with defaults and validators
- Settings store in `src/syntara/settings/store.py` — data access layer
- REST API at `/api/v1/settings` — list, get, update, bulk update (in progress)

**Access pattern:** Runtime settings are read from the database via the settings store, not through `get_settings()`. The two systems are independent — `get_settings()` remains the correct access path for all environment-based configuration documented in this file.

See `docs/runtime-settings.md` for the full GSF guide.

## Reference

| File | Purpose |
|---|---|
| `src/syntara/core/config/base.py` | Main Settings class and all domain settings |
| `src/syntara/core/config/__init__.py` | Package exports |
| `src/syntara/settings/catalog.py` | Runtime settings catalog (GSF) |
| `src/syntara/settings/store.py` | Runtime settings data access (GSF) |
| `.env.example` | Template for all configuration variables |
| `tests/unit/core/config/test_config.py` | Configuration test suite |

Generated By: Claude Code (Claude Opus 4.6)
