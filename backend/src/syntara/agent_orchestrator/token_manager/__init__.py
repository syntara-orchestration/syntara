"""Token Manager - LLM Token Counting and Validation System.

This module provides token counting and validation services for LLM requests,
tracking usage per user with rolling time windows.

Public API:
    - TokenValidationService: Main service for token validation
    - TokenCalculator: Token counting using tiktoken
    - TokenUsageRepository: Data access for token usage and configuration
    - TokenLimitExceededError: Exception raised when token limit is exceeded
    - UserTokenConfigNotFoundError: Exception raised when user config is missing
    - TokenCalculationError: Exception raised when token calculation fails
"""

from syntara.agent_orchestrator.token_manager.exceptions import (
    TokenCalculationError,
    TokenLimitExceededError,
    TokenValidationError,
    UserTokenConfigNotFoundError,
)
from syntara.agent_orchestrator.token_manager.models import TokenUsageRecord, UserTokenConfig
from syntara.agent_orchestrator.token_manager.repository import TokenUsageRepository
from syntara.agent_orchestrator.token_manager.services import TokenCalculator, TokenValidationService

__all__ = [
    "TokenCalculationError",
    "TokenCalculator",
    "TokenLimitExceededError",
    "TokenUsageRecord",
    "TokenUsageRepository",
    "TokenValidationError",
    "TokenValidationService",
    "UserTokenConfig",
    "UserTokenConfigNotFoundError",
]
