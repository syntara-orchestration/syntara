"""Auto-discovery of AuditEventHandler subclasses."""

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, ForwardRef, get_args, get_origin

import structlog

from syntara.audit.handler import AuditEventHandler

logger = structlog.stdlib.get_logger(__name__)


def _resolve_forward_ref(ref: ForwardRef, handler_cls: type) -> type | None:
    """Attempt to resolve a ForwardRef by looking up the name in the handler's module."""
    module_name = getattr(handler_cls, "__module__", None)
    if not module_name or module_name not in sys.modules:
        return None
    resolved = vars(sys.modules[module_name]).get(ref.__forward_arg__)
    return resolved if isinstance(resolved, type) else None


def get_event_type(handler_cls: type[AuditEventHandler[Any]]) -> type | None:
    """Extract the event type ``T`` from ``AuditEventHandler[T]``.

    Walks the MRO's ``__orig_bases__`` chain to find the first
    parameterised ``AuditEventHandler`` ancestor. This supports both
    direct subclasses (``class H(AuditEventHandler[E])``) and
    multi-level inheritance (``class H(BaseH)`` where
    ``BaseH(AuditEventHandler[E])``).

    Returns ``None`` if no parameterised ``AuditEventHandler`` ancestor
    is found (e.g. a raw ``AuditEventHandler`` subclass without a
    type argument).
    """
    for cls in handler_cls.__mro__:
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is AuditEventHandler:
                args = get_args(base)
                if args:
                    arg = args[0]
                    if isinstance(arg, ForwardRef):
                        return _resolve_forward_ref(arg, cls)
                    return arg if isinstance(arg, type) else None
    return None


def _validate_package_scope(package: ModuleType) -> bool:
    """Validate that package is within the syntara.* hierarchy.

    Returns True if valid, False otherwise. Logs error on validation failure.
    """
    package_name = package.__name__
    if not package_name.startswith("syntara."):
        logger.error(
            "Audit handler discovery restricted to syntara.* packages",
            package=package_name,
        )
        return False
    return True


def _get_expected_base_path(package: ModuleType) -> Path | None:
    """Extract and resolve the base filesystem path for the package.

    Returns None if the package has no __path__ attribute.
    """
    if not hasattr(package, "__path__"):
        return None
    try:
        return Path(package.__path__[0]).resolve()
    except (IndexError, OSError):
        return None


def _validate_module_name(module_name: str, expected_prefix: str) -> bool:
    """Validate module name matches expected package hierarchy.

    Returns True if valid, False otherwise. Logs error on validation failure.
    """
    if not module_name.startswith(expected_prefix):
        logger.error(
            "Audit handler discovery rejected module outside expected package hierarchy",
            module=module_name,
            expected_prefix=expected_prefix,
        )
        return False
    return True


def _validate_module_path(module: ModuleType, expected_base_path: Path | None) -> bool:
    """Validate module's file path is within expected base directory.

    Returns True if valid, False otherwise. Logs error on validation failure.
    Skips validation if module has no __file__ or expected_base_path is None.
    """
    if not hasattr(module, "__file__") or not module.__file__ or not expected_base_path:
        return True

    try:
        module_path = Path(module.__file__).resolve()
        if not module_path.is_relative_to(expected_base_path):
            logger.error(
                "Audit handler discovery rejected module with file path outside expected base",
                module=module.__name__,
                module_file=str(module_path),
                expected_base=str(expected_base_path),
            )
            return False
    except (ValueError, OSError):
        logger.exception(
            "Audit handler discovery could not validate module file path",
            module=module.__name__,
        )
        return False

    return True


def _is_concrete_handler_class(obj: type) -> bool:
    """Check if a class is a concrete AuditEventHandler subclass.

    Returns True if obj is a concrete (non-abstract) subclass of AuditEventHandler,
    but not AuditEventHandler itself.
    """
    try:
        if not issubclass(obj, AuditEventHandler):
            return False
        if obj is AuditEventHandler:
            return False
        return not inspect.isabstract(obj)
    except TypeError:
        # issubclass raises TypeError for non-class objects
        return False


def _try_instantiate_handler(
    handler_cls: type[AuditEventHandler[Any]],
    event_type: type,
) -> AuditEventHandler[Any] | None:
    """Attempt to instantiate a handler class.

    Returns handler instance on success, None on failure. Logs exception on failure.
    """
    try:
        return handler_cls()
    except Exception:
        logger.exception(
            "Audit handler instantiation failed — skipping. Handlers must be zero-arg constructable.",
            handler=handler_cls.__qualname__,
            event_type=getattr(event_type, "__qualname__", repr(event_type)),
        )
        return None


def _import_module_safe(module_name: str) -> ModuleType | None:
    """Safely import a module by name.

    Returns module on success, None on failure. Logs exception on failure.
    """
    try:
        return importlib.import_module(module_name)
    except Exception:
        logger.exception(
            "Audit handler discovery failed to import module",
            module=module_name,
        )
        return None


def _process_module_for_handlers(module: ModuleType) -> dict[type, AuditEventHandler[Any]]:
    """Extract and instantiate all handler classes from a module.

    Returns dict mapping event types to handler instances for all valid handlers found.
    """
    handlers: dict[type, AuditEventHandler[Any]] = {}

    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if not _is_concrete_handler_class(obj):
            continue

        event_type = get_event_type(obj)
        if event_type is None:
            logger.warning(
                "Audit handler has no resolvable AuditEventHandler[T] ancestor — skipping. "
                "Either the type parameter is missing or it could not be walked via __orig_bases__.",
                handler=obj.__qualname__,
            )
            continue

        instance = _try_instantiate_handler(obj, event_type)
        if instance is None:
            continue

        handlers[event_type] = instance
        logger.debug(
            "Registered audit handler",
            handler=obj.__qualname__,
            event_type=getattr(event_type, "__qualname__", repr(event_type)),
        )

    return handlers


def discover_handlers(package: ModuleType) -> dict[type, AuditEventHandler[Any]]:
    """Walk *package* and return a registry of ``{event_type: handler_instance}``.

    Every concrete :class:`AuditEventHandler` subclass found under
    *package* is instantiated (zero-arg constructor) and registered
    against the event type extracted from its generic parameter.
    Handlers must therefore be zero-arg constructable; see
    :class:`AuditEventHandler` for the full contract.

    Callers should pass a domain-scoped audit package (e.g. ``syntara.auth.audit``),
    not the top-level application package — walking broad packages triggers
    import-time side effects across the entire codebase.

    **Security:** Discovery is restricted to the ``syntara.*`` package hierarchy.
    Modules are validated to ensure their name and file path remain within
    the expected package scope, preventing symlink attacks or filesystem
    traversal exploits.

    Handlers whose event type cannot be determined are skipped with a
    warning. Modules that fail to import, and handlers that fail to
    instantiate, are logged at error level with traceback and skipped —
    silent coverage loss is harder to diagnose than a loud startup error,
    but a single broken handler should not prevent the rest from loading.
    """
    # Validate package scope before discovery
    if not _validate_package_scope(package):
        return {}

    registry: dict[type, AuditEventHandler[Any]] = {}
    expected_prefix = package.__name__
    expected_base_path = _get_expected_base_path(package)

    for _importer, module_name, _ispkg in pkgutil.walk_packages(
        package.__path__,
        package.__name__ + ".",
    ):
        # Validate module name matches expected hierarchy
        if not _validate_module_name(module_name, expected_prefix):
            continue

        # Safely import the module
        module = _import_module_safe(module_name)
        if module is None:
            continue

        # Validate module file path is within expected base directory
        if not _validate_module_path(module, expected_base_path):
            continue

        # Extract and register handlers from the module
        module_handlers = _process_module_for_handlers(module)
        registry.update(module_handlers)

    return registry
