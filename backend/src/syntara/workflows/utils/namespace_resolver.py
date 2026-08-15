"""Template expression resolver for v2 workflows."""

import copy
import re
from typing import Any

TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")


class NamespaceResolver:
    """Resolves template expressions like ${trigger.url} to actual values."""

    def __init__(self) -> None:
        """Initialize resolver with empty namespaces."""
        self.namespaces: dict[str, dict[str, Any]] = {}
        self._loop_node_id: str | None = None

    def set_context(self, *, loop_node_id: str | None = None) -> None:
        """Set execution context for smart namespace resolution.

        Args:
            loop_node_id: ID of the enclosing loop node for the current node

        """
        self._loop_node_id = loop_node_id

    def set_namespace(self, namespace_name: str, data: dict[str, Any]) -> None:
        """Set data for a namespace.

        Args:
            namespace_name: Name of namespace (e.g., "trigger", "fetch_data")
            data: Data to store in that namespace

        """
        self.namespaces[namespace_name] = data

    def has_namespace(self, namespace_name: str) -> bool:
        """Check if a namespace exists.

        Args:
            namespace_name: Name of namespace to check

        Returns:
            True if namespace exists

        """
        return namespace_name in self.namespaces

    def remove_namespace(self, namespace_name: str) -> None:
        """Remove a namespace.

        Args:
            namespace_name: Name of namespace to remove

        """
        if namespace_name in self.namespaces:
            del self.namespaces[namespace_name]

    def get_namespace(self, namespace_name: str) -> dict[str, Any]:
        """Get data for a namespace.

        Args:
            namespace_name: Name of namespace to retrieve

        Returns:
            Namespace data

        Raises:
            KeyError: If namespace not found

        """
        return self.namespaces[namespace_name]

    def get_all_namespaces(self) -> dict[str, dict[str, Any]]:
        """Get all namespaces.

        Returns:
            Dictionary of all namespaces

        """
        return self.namespaces

    def get_complete_namespace(self) -> dict[str, Any]:
        """Get complete namespace for context-aware evaluation.

        Returns all namespaces flattened into a single dict for condition evaluation.
        Loop context is exposed as 'loop' namespace if loop_node_id is set.

        Returns:
            Complete namespace dict with all available data (deep copy)

        Example:
            >>> resolver.set_namespace("input", {"age": 25})
            >>> resolver.set_namespace("fetch_user", {"role": "admin"})
            >>> resolver.get_complete_namespace()
            {'input': {'age': 25}, 'fetch_user': {'role': 'admin'}}

        """
        # Deep copy of namespaces for defense-in-depth isolation.
        # While Temporal's serialization provides process isolation between activities,
        # the deep copy ensures the AST evaluator cannot mutate workflow state even if
        # a custom __eq__ method or future code path inadvertently modifies namespace values.
        # Performance note: For workflows with 50+ nodes and large JSON payloads, this may
        # become expensive. If profiling shows this as a bottleneck, consider switching to
        # shallow copy (dict(self.namespaces)) with explicit documentation that namespace
        # values must not be mutated.
        namespace = copy.deepcopy(self.namespaces)

        # If loop context is set, expose the current loop's data as 'loop' namespace
        # This allows ${loop.item} and ${loop.index} to work in conditions
        if self._loop_node_id and "loop" in namespace:
            loop_data = namespace["loop"].get(self._loop_node_id, {})
            namespace["loop"] = loop_data

        return namespace

    def resolve_value(self, value: Any) -> Any:  # noqa: ANN401
        """Resolve template expressions in a value.

        Args:
            value: Value that may contain template expressions

        Returns:
            Resolved value with templates replaced

        """
        if not isinstance(value, str):
            return value

        # Check if entire value is a single template
        match = TEMPLATE_PATTERN.fullmatch(value)
        if match:
            return self._lookup_path(match.group(1))

        # Replace multiple templates in string
        def replacer(match: re.Match[str]) -> str:
            result = self._lookup_path(match.group(1))
            return str(result)

        return TEMPLATE_PATTERN.sub(replacer, value)

    def resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve template expressions in a dictionary.

        Args:
            data: Dictionary that may contain template expressions

        Returns:
            New dictionary with templates resolved

        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self.resolve_dict(value)
            elif isinstance(value, list):
                result[key] = self._resolve_list(value)
            else:
                result[key] = self.resolve_value(value)
        return result

    def _resolve_list(self, items: list[Any]) -> list[Any]:
        """Recursively resolve template expressions in a list.

        Args:
            items: List that may contain dicts, nested lists, or template strings

        Returns:
            New list with templates resolved

        """
        resolved: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                resolved.append(self.resolve_dict(item))
            elif isinstance(item, list):
                resolved.append(self._resolve_list(item))
            else:
                resolved.append(self.resolve_value(item))
        return resolved

    def _lookup_path(self, path: str) -> Any:  # noqa: ANN401
        """Look up a dotted path like 'trigger.url' in namespaces.

        Supports smart loop resolution: ${loop.item} automatically finds
        the closest upstream loop node and resolves to ${loop_node_id.loop.item}.

        Args:
            path: Dotted path to look up

        Returns:
            Value at that path

        Raises:
            KeyError: If path not found

        """
        parts = path.split(".")
        namespace_name = parts[0]

        # Smart loop resolution: always translate loop.* to loop.{loop_node_id}.*
        # This keeps loop namespace separate and doesn't pollute node namespaces
        if namespace_name == "loop":
            loop_node_id = self._find_upstream_loop()
            if loop_node_id:
                # Rewrite path: loop.item → loop.{loop_node_id}.item
                path = f"loop.{loop_node_id}.{'.'.join(parts[1:])}" if len(parts) > 1 else f"loop.{loop_node_id}"
                parts = path.split(".")

        if namespace_name not in self.namespaces:
            msg = (
                f'Step "{namespace_name}" was not found or has not produced output yet.'
                " Check that the referenced step name is correct and that it runs"
                " before this step in the workflow."
            )
            raise KeyError(msg)

        result: Any = self.namespaces[namespace_name]
        for part in parts[1:]:
            if isinstance(result, dict):
                if part not in result:
                    msg = f'Property "{part}" not found in step "{namespace_name}" output at path "{path}"'
                    raise KeyError(msg)
                result = result[part]
            elif isinstance(result, list):
                try:
                    result = result[int(part)]
                except (ValueError, IndexError) as exc:
                    msg = f'Invalid list index "{part}" in step "{namespace_name}" output at path "{path}"'
                    raise KeyError(msg) from exc
            else:
                msg = f"Cannot traverse into {type(result).__name__} with key '{part}' in path '{path}'"
                raise KeyError(msg)

        return result

    def _find_upstream_loop(self) -> str | None:
        """Return the enclosing loop node ID set via set_context.

        Returns:
            Loop node ID if the current node is inside a loop body, None otherwise

        """
        return self._loop_node_id

    def snapshot(self) -> dict[str, Any]:
        """Export current namespace state for breakpoint/resume.

        Returns:
            Dict with deep copies of namespaces and loop context

        """
        return {
            "namespaces": copy.deepcopy(self.namespaces),
            "loop_node_id": self._loop_node_id,
        }

    def restore(self, state: dict[str, Any]) -> None:
        """Restore namespace state from a snapshot.

        Args:
            state: State dict previously returned by snapshot()

        """
        self.namespaces = copy.deepcopy(state["namespaces"])
        self._loop_node_id = state.get("loop_node_id")
