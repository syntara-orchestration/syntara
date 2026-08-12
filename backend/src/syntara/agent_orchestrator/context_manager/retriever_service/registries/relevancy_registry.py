"""Registry for managing relevancy checker implementations and configurations.

This module provides the RelevancyRegistry class for registering and managing
different RelevancyChecker implementations with their associated configurations.
"""

import functools
from typing import Any

import structlog

from syntara.agent_orchestrator.context_manager.retriever_service.checkers.keyword_relevancy_checker import (
    KeywordRelevancyChecker,
)
from syntara.agent_orchestrator.context_manager.retriever_service.checkers.llm_relevancy_checker import (
    LLMRelevancyChecker,
)
from syntara.agent_orchestrator.context_manager.retriever_service.config.configuration_manager import (
    ConfigurationManager,
)
from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RegistryError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.relevancy_checker import RelevancyChecker
from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
    RelevancyConfiguration,
)

logger = structlog.stdlib.get_logger(__name__)


class RelevancyRegistry:
    """Registry for managing relevancy checker implementations and their configurations.

    This class implements the Registry pattern to allow dynamic registration
    and retrieval of RelevancyChecker implementations with their associated
    configurations. This enables the RetrieverService to use different
    relevancy checking algorithms without knowing their specific implementations.

    The registry supports:
    - Registration of new checker types with configurations
    - Type-safe checker instantiation
    - Configuration management per checker type
    - Enumeration of available checkers
    - Error handling for invalid operations

    Example Usage:
        ```python
        registry = RelevancyRegistry()

        # Register checkers with configurations
        llm_config = RelevancyConfiguration(
            checker_type="llm",
            similarity_threshold=0.7,
            max_results=10,
            algorithm_parameters={"temperature": 0.3}
        )
        registry.register_checker("llm", LLMRelevancyChecker, llm_config)

        keyword_config = RelevancyConfiguration(
            checker_type="keyword",
            similarity_threshold=0.5,
            max_results=15
        )
        registry.register_checker("keyword", KeywordRelevancyChecker, keyword_config)

        # Get specific checker
        checker = registry.get_checker("llm")
        config = registry.get_configuration("llm")

        # Get primary checker with fallback
        primary_checker = registry.get_primary_checker()
        fallback_checker = registry.get_fallback_checker()
        ```
    """

    def __init__(self) -> None:
        """Initialize relevancy registry with default implementations."""
        self._checkers: dict[str, type[RelevancyChecker]] = {}
        self._configurations: dict[str, RelevancyConfiguration] = {}
        self._primary_checker: str | None = None
        self._fallback_checker: str | None = None

    def register_checker(self, name: str, checker_class: type[Any], config: RelevancyConfiguration) -> None:
        """Register a relevancy checker implementation with its configuration.

        Args:
            name: Unique identifier for this checker type
            checker_class: RelevancyChecker subclass to register
            config: Configuration settings for this checker

        Raises:
            RegistryError: If checker name is already registered or config type mismatch
            TypeError: If checker_class is not a RelevancyChecker subclass

        """
        if not name or not name.strip():
            error_msg = "Checker name cannot be empty"
            raise RegistryError(error_msg)

        if not issubclass(checker_class, RelevancyChecker):
            error_msg = f"Checker class must be a subclass of RelevancyChecker, got {checker_class}"
            raise TypeError(error_msg)

        if name in self._checkers:
            error_msg = f"Checker '{name}' is already registered"
            raise RegistryError(error_msg)

        # Validate configuration type matches checker name
        if config.checker_type != name:
            error_msg = f"Configuration checker_type '{config.checker_type}' does not match registration name '{name}'"
            raise RegistryError(error_msg)

        self._checkers[name] = checker_class
        self._configurations[name] = config

        # Set primary and fallback if this is the first registration
        if self._primary_checker is None:
            self._primary_checker = name
            logger.info("Set primary checker", checker_name=name)
        elif self._fallback_checker is None and name != self._primary_checker:
            self._fallback_checker = name
            logger.info("Set fallback checker", checker_name=name)

        logger.info("Registered relevancy checker", checker_name=name, checker_class=checker_class.__name__)

    def get_checker(self, name: str) -> RelevancyChecker:
        """Get a relevancy checker instance by name.

        Args:
            name: Name of the registered checker

        Returns:
            New instance of the requested checker

        Raises:
            RegistryError: If checker name is not registered

        """
        if name not in self._checkers:
            error_msg = f"Checker '{name}' is not registered. Available: {list(self._checkers.keys())}"
            raise RegistryError(error_msg)

        checker_class = self._checkers[name]
        checker_instance = checker_class()

        logger.debug("Created checker instance", checker_name=name)
        return checker_instance

    def get_configuration(self, name: str) -> RelevancyConfiguration:
        """Get configuration for a registered checker.

        Args:
            name: Name of the registered checker

        Returns:
            Configuration for the requested checker

        Raises:
            RegistryError: If checker name is not registered

        """
        if name not in self._configurations:
            error_msg = f"Configuration for checker '{name}' not found. Available: {list(self._configurations.keys())}"
            raise RegistryError(error_msg)

        return self._configurations[name]

    def update_configuration(self, name: str, config: RelevancyConfiguration) -> None:
        """Update configuration for a registered checker.

        Args:
            name: Name of the registered checker
            config: New configuration settings

        Raises:
            RegistryError: If checker is not registered or config type mismatch

        """
        if name not in self._checkers:
            error_msg = f"Checker '{name}' is not registered"
            raise RegistryError(error_msg)

        # Validate configuration type matches checker name
        if config.checker_type != name:
            error_msg = f"Configuration checker_type '{config.checker_type}' does not match checker name '{name}'"
            raise RegistryError(error_msg)

        old_config = self._configurations[name]
        self._configurations[name] = config

        logger.info("Updated configuration for checker", checker_name=name)
        logger.debug("Old config", old_config=old_config.model_dump())
        logger.debug("New config", new_config=config.model_dump())

    def get_primary_checker(self) -> tuple[RelevancyChecker, RelevancyConfiguration] | None:
        """Get the primary relevancy checker and its configuration.

        The primary checker is typically an LLM-based checker that provides
        the most accurate relevancy scoring but may fail occasionally.

        Returns:
            Tuple of (checker_instance, configuration) or None if no checkers registered

        """
        if not self._primary_checker:
            return None

        checker = self.get_checker(self._primary_checker)
        config = self.get_configuration(self._primary_checker)

        logger.debug("Retrieved primary checker", checker_name=self._primary_checker)
        return checker, config

    def get_fallback_checker(self) -> tuple[RelevancyChecker, RelevancyConfiguration] | None:
        """Get the fallback relevancy checker and its configuration.

        The fallback checker is typically a keyword-based checker that is
        more reliable but less accurate than the primary checker.

        Returns:
            Tuple of (checker_instance, configuration) or None if no fallback available

        """
        if not self._fallback_checker:
            return None

        checker = self.get_checker(self._fallback_checker)
        config = self.get_configuration(self._fallback_checker)

        logger.debug("Retrieved fallback checker", checker_name=self._fallback_checker)
        return checker, config

    def set_primary_checker(self, name: str) -> None:
        """Set the primary relevancy checker.

        Args:
            name: Name of registered checker to use as primary

        Raises:
            RegistryError: If checker name is not registered

        """
        if name not in self._checkers:
            error_msg = f"Checker '{name}' is not registered"
            raise RegistryError(error_msg)

        old_primary = self._primary_checker
        self._primary_checker = name

        logger.info("Changed primary checker", old_primary=old_primary, new_primary=name)

    def set_fallback_checker(self, name: str) -> None:
        """Set the fallback relevancy checker.

        Args:
            name: Name of registered checker to use as fallback

        Raises:
            RegistryError: If checker name is not registered

        """
        if name not in self._checkers:
            error_msg = f"Checker '{name}' is not registered"
            raise RegistryError(error_msg)

        old_fallback = self._fallback_checker
        self._fallback_checker = name

        logger.info("Changed fallback checker", old_fallback=old_fallback, new_fallback=name)

    def list_checkers(self) -> list[str]:
        """List names of all registered checkers.

        Returns:
            List of registered checker names

        """
        return list(self._checkers.keys())

    def get_all_checkers(self) -> dict[str, tuple[RelevancyChecker, RelevancyConfiguration]]:
        """Get instances and configurations of all registered checkers.

        Returns:
            Dictionary mapping checker names to (instance, configuration) tuples

        """
        all_checkers = {}
        for name in self._checkers:
            checker_instance = self.get_checker(name)
            config = self.get_configuration(name)
            all_checkers[name] = (checker_instance, config)

        logger.debug("Created instances for checkers", checker_count=len(all_checkers))
        return all_checkers


# ===================================================
# Generator for dependency injection
# ---------------------------------------------------
def _setup_default_registry() -> "RelevancyRegistry":
    """Set up default relevancy registry with LLM and keyword checkers."""
    registry: RelevancyRegistry = RelevancyRegistry()
    config_manager = ConfigurationManager()

    # Register LLM checker as primary
    llm_config = config_manager.get_llm_configuration()
    registry.register_checker("llm", LLMRelevancyChecker, llm_config)

    # Register keyword checker as fallback
    keyword_config = config_manager.get_keyword_configuration()
    registry.register_checker("keyword", KeywordRelevancyChecker, keyword_config)

    # Set primary and fallback explicitly
    registry.set_primary_checker("llm")
    registry.set_fallback_checker("keyword")

    logger.info("Initialized RelevancyRegistry with default checkers", checker_count=len(registry.list_checkers()))

    return registry


@functools.lru_cache(maxsize=1)
def get_relevancy_registry() -> RelevancyRegistry:
    """Get relevancy registry for dependency injection.

    Returns:
        RelevancyRegistry for dependency injection

    Example:
        from syntara.agent_orchestrator.context_manager.retriever_service.registries.relevancy_registry import (
            get_relevancy_registry,
        )

        registry = get_relevancy_registry()
        primary_checker, config = registry.get_primary_checker()
        score = await primary_checker.check_relevancy(document, prompt, config)

    """
    return _setup_default_registry()


# ===================================================
