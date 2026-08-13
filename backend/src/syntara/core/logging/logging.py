"""Setup logging."""

import json
import logging
from logging import Formatter
from typing import Any

import structlog
from structlog.processors import JSONRenderer
from structlog.typing import (
    EventDict,
    WrappedLogger,
)

from syntara.core.config.base import LogLevel, get_settings
from syntara.core.logging.otel_handlers import create_otel_handler
from syntara.settings.watch import watch_setting

settings = get_settings()

_UVICORN_LOGGER_NAMES = ("uvicorn", "uvicorn.error", "uvicorn.access")


class NexusLogRecordRenderer(JSONRenderer):
    """Renderer that outputs JSON."""

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize renderer.

        Args:
            **kwargs: Additional arguments passed to JSONRenderer

        """
        super().__init__(**kwargs)

    def __call__(self, _: WrappedLogger, __: str, event_dict: EventDict) -> str | bytes:
        """Render event dictionary as JSON."""
        return self._render_json(event_dict)

    def _make_serializable(self, obj: object) -> object:
        """Recursively convert non-JSON-serializable objects to strings using __repr__."""
        if isinstance(obj, str | int | float | bool | type(None)):
            return obj
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [self._make_serializable(item) for item in obj]
        # Try JSON serialization first, fall back to __repr__ if it fails
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return repr(obj)

    def _render_json(self, event_dict: EventDict) -> str:
        serializable_dict = self._make_serializable(event_dict)
        return str(self._dumps(serializable_dict, **self._dumps_kw))


def build_nexus_shared_formatters() -> list[Any]:
    """Build shared formatters for stdlib logging for structured logs."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
    ]


def build_nexus_formatter() -> Formatter:
    """Configure Nexus log formatter."""
    if settings.log_output_format == "text":
        return build_nexus_text_formatter()
    return build_nexus_json_formatter()


def build_nexus_text_formatter() -> Formatter:
    """Build a simple text formatter for plain text logging."""
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        foreign_pre_chain=build_nexus_shared_formatters(),
    )


def build_nexus_json_formatter() -> Formatter:
    """Build a JSON formatter using NexusLogRecordRenderer."""
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            NexusLogRecordRenderer(),
        ],
        foreign_pre_chain=build_nexus_shared_formatters(),
    )


def build_uvicorn_logging_config(log_level: str) -> dict[str, Any]:
    """Build uvicorn logging configuration dict.

    Args:
        log_level: The log level string (e.g. "INFO", "DEBUG").

    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "nexus": {
                "()": "syntara.core.logging.logging.build_nexus_formatter",
            },
        },
        "handlers": {
            "nexus": {
                "formatter": "nexus",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            name: {"handlers": ["nexus"], "level": log_level, "propagate": False} for name in _UVICORN_LOGGER_NAMES
        },
        "root": {
            "handlers": ["nexus"],
            "level": log_level,
        },
    }


def _set_log_level(level: str) -> None:
    """Set the log level on all relevant loggers."""
    root = logging.getLogger()
    root.setLevel(level)
    for name in _UVICORN_LOGGER_NAMES:
        logging.getLogger(name).setLevel(level)


async def apply_runtime_log_level() -> None:
    """Apply the runtime log level setting to all loggers.

    Called after the database is available.  Falls back to the static
    config log_level if the runtime setting cannot be read.

    This function intentionally bridges ``core.logging`` and
    ``settings.cache`` -- it reads a runtime setting and applies it to
    loggers.  The inline import keeps the compile-time dependency graph
    clean while co-locating the logic with the logger manipulation it
    performs.
    """
    from syntara.settings.cache.settings_cache import get_runtime_settings  # noqa: PLC0415

    log = logging.getLogger(__name__)
    fallback_level = settings.fallback_log_level
    try:
        cache = get_runtime_settings()
        level = await cache.get_str(
            "logging.log_level",
            default=fallback_level,
        )
        level = level.upper()
    except Exception:  # noqa: BLE001
        log.warning(
            "settings.runtime_log_level_read_error",
            extra={"fallback_level": fallback_level},
            exc_info=True,
        )
        level = fallback_level

    if level != fallback_level:
        log.info(
            "settings.runtime_log_level_override",
            extra={"fallback_level": fallback_level, "level": level},
        )
    else:
        log.info("settings.log_level_applied", extra={"level": level})

    _set_log_level(level)


@watch_setting("logging.log_level")
def _on_log_level_changed(_key: str, new_value: Any) -> None:  # noqa: ANN401
    """Apply a changed log level value from the database."""
    level = str(new_value).upper()
    if level not in LogLevel.__members__:
        logging.getLogger(__name__).warning(
            "settings.invalid_log_level_ignored",
            extra={"value": new_value},
        )
        return
    logging.getLogger(__name__).info(
        "settings.runtime_log_level_changed",
        extra={"level": level},
    )
    _set_log_level(level)


def configure_app_logging() -> None:
    """Configure structlog and stdlib logging for structured logs."""
    # Always attach stdout handler
    handler = logging.StreamHandler()
    handler.setFormatter(build_nexus_formatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.fallback_log_level)

    # Create and attach OTLP handler if enabled
    otel_handler = create_otel_handler()
    if otel_handler is not None:
        root_logger.addHandler(otel_handler)
        logging.getLogger(__name__).info(
            "logging.root_otel_configured",
            extra={
                "endpoint": settings.otel_endpoint,
                "service_name": settings.otel_service_name,
            },
        )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *build_nexus_shared_formatters(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
