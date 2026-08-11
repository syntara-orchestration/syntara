"""LLM-based relevancy checker with OpenRouter integration.

This module provides an LLM-based relevancy checker that uses OpenRouter
to access various language models for sophisticated document relevancy scoring.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from syntara.agent_orchestrator.clients.openrouter_config import get_openrouter_llm
from syntara.agent_orchestrator.context_manager.retriever_service.exceptions import RelevancyCheckError
from syntara.agent_orchestrator.context_manager.retriever_service.interfaces.relevancy_checker import RelevancyChecker
from syntara.core.constants import RetrieverServiceDefaults
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.instrumentation import record_llm_call

if TYPE_CHECKING:
    from syntara.agent_orchestrator.context_manager.retriever_service.models.relevancy_configuration import (
        RelevancyConfiguration,
    )
    from syntara.agent_orchestrator.context_manager.retriever_service.models.relevant_document import RelevantDocument
    from syntara.agent_orchestrator.models.llm_credential_config import LLMCredentialConfig

logger = structlog.stdlib.get_logger(__name__)


class LLMRelevancyChecker(RelevancyChecker):
    """LLM-based relevancy checker using OpenRouter integration.

    This implementation uses large language models via OpenRouter to provide
    sophisticated semantic relevancy scoring that considers:

    - Semantic meaning and context
    - Document structure and format
    - File metadata and naming
    - Query intent and specificity
    - Content quality and depth

    The checker is designed as the primary relevancy assessment method,
    with keyword-based fallback when LLM calls fail.

    Features:
    - Model selection via LLMCredentialConfig
    - Temperature and max_tokens control
    - Custom system prompts for scoring guidance
    - File metadata integration for enhanced context
    - Robust error handling with detailed logging
    - Response parsing with fallback scoring

    Example Usage:
        ```python
        checker = LLMRelevancyChecker()
        config = RelevancyConfiguration(
            checker_type="llm",
            algorithm_parameters={
                "temperature": 0.3,
                "max_tokens": 150,
                "system_prompt": "Score document relevance from 0.0 to 1.0..."
            }
        )

        score = await checker.check_relevancy(
            document, "machine learning", config,
            llm_credential_config=credential,
        )
        ```
    """

    def __init__(self) -> None:
        """Initialize LLM relevancy checker."""
        self.default_system_prompt = RetrieverServiceDefaults.LLM_SYSTEM_PROMPT
        logger.debug("Initialized LLMRelevancyChecker")

    async def check_relevancy(
        self,
        document: RelevantDocument,
        query: str,
        config: RelevancyConfiguration,
        llm_credential_config: LLMCredentialConfig | None = None,
    ) -> float:
        """Check relevancy of document against query using LLM analysis.

        Args:
            document: Document to check for relevancy
            query: Query string to match against
            config: Configuration settings for LLM checking
            llm_credential_config: Credential config from the agentic node

        Returns:
            Relevancy score between 0.0 and 1.0

        Raises:
            RelevancyCheckError: If LLM relevancy checking fails

        """
        try:
            logger.debug("Starting LLM relevancy check for document", filename=document.file_metadata.filename)

            # Extract algorithm parameters and resolve credential
            params = config.algorithm_parameters
            temperature = cast("float", params.get("temperature"))
            max_tokens = cast("int", params.get("max_tokens"))
            system_prompt = cast("str", params.get("system_prompt"))
            api_key, base_url, model, insecure_skip_tls_verify, ca_certificate = self._resolve_llm_params(
                llm_credential_config
            )

            # Build context with file metadata if enabled
            grounding_params = config.grounding_parameters
            include_metadata = cast("bool", grounding_params.get("include_file_metadata"))
            use_title_weighting = cast("bool", grounding_params.get("use_title_weighting"))
            context_window = cast("int", grounding_params.get("context_window_size"))

            # Prepare content for LLM (truncate if needed)
            content_excerpt = self._prepare_content_excerpt(document.content, context_window)

            # Build prompt with metadata context
            user_prompt = self._build_user_prompt(
                query=query,
                content=content_excerpt,
                document=document,
                include_metadata=include_metadata,
                use_title_weighting=use_title_weighting,
            )

            # Get OpenRouter LLM instance
            llm_http_client = None
            try:
                llm, llm_http_client = await get_openrouter_llm(
                    model=model,
                    temperature=temperature,
                    api_key=api_key,
                    base_url=base_url,
                    insecure_skip_tls_verify=insecure_skip_tls_verify,
                    ca_certificate=ca_certificate,
                )
            except Exception as e:
                logger.exception("Failed to get OpenRouter LLM instance")
                error_msg = f"LLM initialization failed: {e!s}"
                raise RelevancyCheckError(error_msg) from e

            # Call LLM for relevancy scoring
            try:
                # Create messages for the LLM
                messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]

                # Invoke LLM (assuming LangChain-compatible interface)
                config_obj = RunnableConfig(configurable={"max_tokens": max_tokens})
                response = await record_llm_call(
                    get_metrics_recorder(),
                    lambda: llm.ainvoke(input=messages, config=config_obj),
                    model=model,
                )

                # Extract response content
                response_text = str(response)
                if hasattr(response, "content"):
                    response_content = response.content
                    if isinstance(response_content, str):
                        response_text = response_content
                    elif isinstance(response_content, list):
                        # Handle list content by joining or using first element
                        response_text = str(response_content[0]) if response_content else ""

                # Parse numeric score from response
                score = self._parse_score_from_response(response_text)

                logger.debug(
                    "LLM relevancy check completed",
                    filename=document.file_metadata.filename,
                    score=score,
                    model=model,
                )

                return score

            except Exception as e:
                logger.exception("LLM API call failed for document", filename=document.file_metadata.filename)
                error_msg = f"LLM API call failed: {e!s}"
                raise RelevancyCheckError(error_msg) from e
            finally:
                if llm_http_client is not None:
                    await llm_http_client.aclose()

        except RelevancyCheckError:
            # Re-raise RelevancyCheckError as-is
            raise

        except Exception as e:
            logger.exception("LLM relevancy check failed for document", filename=document.file_metadata.filename)
            error_msg = f"LLM relevancy check failed: {e!s}"
            raise RelevancyCheckError(error_msg) from e

    def _prepare_content_excerpt(self, content: str, max_length: int) -> str:
        """Prepare content excerpt for LLM processing with intelligent truncation.

        Args:
            content: Full document content
            max_length: Maximum character length for excerpt

        Returns:
            Prepared content excerpt

        """
        if not content:
            return ""

        if len(content) <= max_length:
            return content

        # Try to truncate at sentence boundaries
        truncated = content[:max_length]

        # Find last complete sentence
        last_sentence_end = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))

        if last_sentence_end > max_length * 0.5:  # Only if we keep at least half
            return truncated[: last_sentence_end + 1] + "\n\n[Content truncated...]"
        # Fallback: truncate at word boundary
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.8:
            return truncated[:last_space] + "...\n\n[Content truncated...]"
        return truncated + "...\n\n[Content truncated...]"

    def _build_user_prompt(
        self, query: str, content: str, document: RelevantDocument, *, include_metadata: bool, use_title_weighting: bool
    ) -> str:
        """Build user prompt with query, content, and optional metadata.

        Args:
            query: User query to evaluate against
            content: Document content excerpt
            document: Full document object with metadata
            include_metadata: Whether to include file metadata in prompt
            use_title_weighting: Whether to emphasize filename in relevancy

        Returns:
            Formatted user prompt for LLM

        """
        prompt_parts = [f"Query: {query}", ""]

        # Add file metadata if requested
        if include_metadata:
            metadata = document.file_metadata
            prompt_parts.extend(
                [
                    "Document Metadata:",
                    f"- Filename: {metadata.filename}",
                    f"- File Type: {metadata.mime_type}",
                    f"- File Size: {metadata.size_bytes} bytes",
                    "",
                ]
            )

            if use_title_weighting:
                prompt_parts.extend(
                    ["Note: Consider the filename when scoring relevance - it often indicates document topic.", ""]
                )

        # Add document content
        prompt_parts.extend(
            [
                "Document Content:",
                content,
                "",
                "Score the relevance of this document to the query from 0.0 (not relevant) to 1.0 (highly relevant):",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_score_from_response(self, response: str) -> float:
        """Parse numeric relevancy score from LLM response.

        Args:
            response: Raw LLM response text

        Returns:
            Parsed score between 0.0 and 1.0

        """
        if not response:
            logger.warning("Empty LLM response, returning default score 0.5")
            return self._get_default_score()

        # Clean response text
        response = response.strip()

        # Try different parsing strategies
        score = self._try_parse_decimal(response)
        if score is not None:
            return score

        score = self._try_parse_whole_number(response)
        if score is not None:
            return score

        score = self._try_parse_percentage(response)
        if score is not None:
            return score

        score = self._try_parse_qualitative(response)
        if score is not None:
            return score

        # Default fallback
        logger.warning(
            "Could not parse relevancy score from LLM response, returning default 0.5", response_preview=response[:100]
        )
        return self._get_default_score()

    @staticmethod
    def _resolve_llm_params(
        llm_credential_config: LLMCredentialConfig | None,
    ) -> tuple[str, str, str, bool, str | None]:
        """Extract api_key, base_url, model, and TLS settings from the credential config."""
        if not llm_credential_config:
            msg = "LLM credential config is required for LLM relevancy checking"
            raise RelevancyCheckError(msg)
        return (
            llm_credential_config.api_key.get_secret_value(),
            llm_credential_config.base_url,
            llm_credential_config.model,
            llm_credential_config.insecure_skip_tls_verify,
            llm_credential_config.ca_certificate,
        )

    def _get_default_score(self) -> float:
        """Get default score when parsing fails."""
        return 0.5

    def _try_parse_decimal(self, response: str) -> float | None:
        """Try to parse decimal number (0.0 to 1.0)."""
        decimal_match = re.search(r"\b(0\.\d+|1\.0+|0\.0+)\b", response)
        if decimal_match:
            try:
                score = float(decimal_match.group(1))
                if 0.0 <= score <= 1.0:
                    return score
            except ValueError:
                pass
        return None

    def _try_parse_whole_number(self, response: str) -> float | None:
        """Try to parse whole number and convert to decimal."""
        # Define constants to avoid magic numbers
        max_ten_scale = 10
        max_hundred_scale = 100

        whole_number_match = re.search(r"\b(\d+)\b", response)
        if whole_number_match:
            try:
                number = int(whole_number_match.group(1))
                if 0 <= number <= max_ten_scale:
                    # Assume 0-10 scale, convert to 0.0-1.0
                    return number / 10.0
                if 0 <= number <= max_hundred_scale:
                    # Assume 0-100 scale, convert to 0.0-1.0
                    return number / 100.0
            except ValueError:
                pass
        return None

    def _try_parse_percentage(self, response: str) -> float | None:
        """Try to parse percentage."""
        max_percentage = 100

        percentage_match = re.search(r"(\d+)%", response)
        if percentage_match:
            try:
                percentage = int(percentage_match.group(1))
                if 0 <= percentage <= max_percentage:
                    return percentage / 100.0
            except ValueError:
                pass
        return None

    def _try_parse_qualitative(self, response: str) -> float | None:
        """Try to parse qualitative indicators."""
        response_lower = response.lower()

        high_indicators = ["high", "very relevant", "excellent"]
        medium_indicators = ["medium", "moderate", "somewhat"]
        low_indicators = ["low", "not relevant", "poor"]

        if any(word in response_lower for word in high_indicators):
            logger.warning("Qualitative 'high' relevance detected, returning 0.8")
            return 0.8
        if any(word in response_lower for word in medium_indicators):
            logger.warning("Qualitative 'medium' relevance detected, returning 0.5")
            return 0.5
        if any(word in response_lower for word in low_indicators):
            logger.warning("Qualitative 'low' relevance detected, returning 0.2")
            return 0.2

        return None
