"""Settings catalog: canonical definitions of categories and settings.

Adding a new category requires a :class:`CategoryDefinition` entry in
:data:`CATEGORY_CATALOG`. Adding a new setting requires a
:class:`SettingDefinition` entry in :data:`SETTINGS_CATALOG`. The
post-migration seeder upserts both catalogs into the database — no
migration is needed for new entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from syntara.core.config.base import LogLevel
from syntara.settings.models.runtime_setting import SettingCategory, SettingValueType


@dataclass
class CategoryDefinition:
    """Canonical definition of a setting category for the startup seeder.

    Attributes:
        slug: Machine key matching ``runtime_settings.category`` values.
        name: Human-readable display name for the UI.
        description: Longer description shown in the UI (e.g. tooltips).
        display_order: Sort position for UI tab rendering (lower = first).

    """

    slug: str
    name: str
    description: str | None = None
    display_order: int = 0


CATEGORY_CATALOG: list[CategoryDefinition] = [
    CategoryDefinition(
        slug="ai_llm",
        name="AI / LLM",
        description="Artificial intelligence and large language model settings",
        display_order=5,
    ),
    CategoryDefinition(
        slug="system",
        name="System",
        description="System-level settings including observability and diagnostics",
        display_order=10,
    ),
    CategoryDefinition(
        slug="context_manager",
        name="Context Manager",
        description="Token limits, retrieval, grounding, compression, and context assembly",
        display_order=20,
    ),
    CategoryDefinition(
        slug="workflow_execution",
        name="Workflow Execution",
        description="Workflow execution timeouts, duration limits, and input constraints",
        display_order=30,
    ),
    CategoryDefinition(
        slug="application",
        name="Application",
        description="Application-level settings including document conversion",
        display_order=40,
    ),
    CategoryDefinition(
        slug="authentication",
        name="Authentication",
        description="Authentication, identity provider, and group sync settings",
        display_order=45,
    ),
    CategoryDefinition(
        slug="integrations",
        name="Integrations",
        description="Integration health check and connection test settings",
        display_order=50,
    ),
    CategoryDefinition(
        slug="rate_limiting",
        name="Rate Limiting",
        description="API rate limiting and throttling settings",
        display_order=55,
    ),
]


class ContextManagerGroup(StrEnum):
    """Group names for context_manager settings."""

    GROUNDING = "Grounding scores"
    TOKEN_LIMITS = "Token limits"  # noqa: S105
    RETRIEVAL = "Retrieval"
    SNIPPETS = "Snippets"
    CONTEXT_ASSEMBLY = "Context assembly"
    PERFORMANCE = "Performance"
    COMPRESSION = "Compression"


class WorkflowEngineGroup(StrEnum):
    """Group names for workflow_execution settings."""

    EXECUTION = "Execution"


class DocumentConversionGroup(StrEnum):
    """Group names for application/document conversion settings."""

    GENERAL = "General"


@dataclass
class SettingDefinition:
    """Canonical definition of a single runtime setting.

    Used by the post-migration seeder to upsert the ``runtime_settings`` table.
    Fields that are not operator-mutable (``value``, ``version``) are
    intentionally absent — the seeder never overwrites them.

    Attributes:
        key: Dot-namespaced setting identifier matching ``RuntimeSetting.key``. Globally unique.
        name: Human-readable display name.
        category: Logical grouping for display and filtering.
        value_type: Expected Python type for UI rendering and validation.
        default_value: Factory default as a native Python type.
        description: Optional longer description shown in the UI.
        depends_on: Dot-namespaced key of a boolean setting that controls
            this setting's visibility. ``None`` means always visible.
        requires_restart: Whether a change takes effect without restart.
        cache_ttl_seconds: Per-setting TTL override; ``None`` uses 60s default.
        validation_schema: Optional constraints dict (min, max,
            allowed_values, pattern).

    """

    key: str
    name: str
    category: SettingCategory
    value_type: SettingValueType
    default_value: int | float | bool | str | list[str] | None
    description: str | None = None
    helper_text: str | None = None
    depends_on: str | None = None
    group: str | None = None
    requires_restart: bool = False
    cache_ttl_seconds: int | None = None
    validation_schema: dict[str, Any] | None = field(default=None)


class AuthenticationGroup(StrEnum):
    """Group names for authentication settings."""

    LOCAL_LOGIN = "Local login"


class MetricsGroup(StrEnum):
    """Group names for metrics settings."""

    OBSERVABILITY = "Observability"


SETTINGS_CATALOG: list[SettingDefinition] = [
    # System settings
    SettingDefinition(
        key="logging.log_level",
        name="System Log Level",
        category=SettingCategory.SYSTEM,
        value_type=SettingValueType.STRING,
        default_value="INFO",
        description=(
            "Determines how much detail the system records. Changes are "
            "applied dynamically without a restart. Logging levels follow a "
            "hierarchical threshold. When you set a level, the application "
            "records everything at that level and above. INFO or WARNING is "
            "standard for production. Use DEBUG only during troubleshooting, "
            "as it creates large volumes of data and can slow down the "
            "application."
        ),
        helper_text="One of: DEBUG, INFO, WARNING, ERROR, CRITICAL",
        requires_restart=False,
        validation_schema={"allowed_values": [level.value for level in LogLevel]},
    ),
    # Metrics — Observability
    SettingDefinition(
        key="metrics.perf_test_mode",
        name="Performance test mode",
        category=SettingCategory.SYSTEM,
        value_type=SettingValueType.BOOLEAN,
        default_value=False,
        description=(
            "Activates the in-memory metrics store and exposes internal "
            "metrics endpoints for performance testing. Raw metric records "
            "are stored in memory and queryable without restarting the "
            "application. Running heavy loads can cause high memory usage. "
            "This mode is designed for short-term testing in non-production "
            "environments, not continuous operation."
        ),
        helper_text="Enable only in non-production environments",
        group=MetricsGroup.OBSERVABILITY,
    ),
    # Context Manager — Grounding scores
    SettingDefinition(
        key="context_manager.required_grounding_score",
        name="Required grounding score",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.FLOAT,
        default_value=0.7,
        description=(
            "The minimum confidence score a retrieved document must achieve "
            "to be included in the context. Documents below this threshold "
            "are excluded entirely. A higher threshold increases accuracy "
            "and reduces hallucinations, but if set too high the system can "
            "refuse to answer valid questions because the retrieval confidence "
            "is not high enough. A lower threshold ensures answers more "
            "often but increases the risk of unfounded claims."
        ),
        helper_text="Range 0.0-1.0",
        group=ContextManagerGroup.GROUNDING,
        validation_schema={"min": 0.0, "max": 1.0},
    ),
    SettingDefinition(
        key="context_manager.minimum_grounding_score",
        name="Minimum grounding score",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.FLOAT,
        default_value=0.5,
        description=(
            "The lowest acceptable confidence score for considering a "
            "retrieved document. Documents between this value and the "
            "required score are included but ranked lower. A lower threshold "
            "ensures the user gets an answer more often but increases the "
            "risk of unfounded claims."
        ),
        helper_text="Range 0.0-1.0. Must be less than or equal to required grounding score.",
        group=ContextManagerGroup.GROUNDING,
        validation_schema={"min": 0.0, "max": 1.0},
    ),
    # Context Manager — Token limits
    SettingDefinition(
        key="context_manager.max_total_tokens",
        name="Max total tokens (fallback)",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=4000,
        description=(
            "Fallback token budget used when the model's context window "
            "cannot be determined automatically from its profile. When a "
            "model profile is available, the budget is derived from the "
            "model's context window minus the output token reserve, with "
            "the tokenizer safety margin applied."
        ),
        helper_text="Minimum 1 token",
        group=ContextManagerGroup.TOKEN_LIMITS,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="context_manager.output_token_reserve",
        name="Output token reserve",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=4096,
        description=(
            "Number of tokens reserved for the LLM's response generation. "
            "This amount is subtracted from the model's context window "
            "before allocating tokens for input context. Higher values "
            "allow longer responses but reduce the budget available for "
            "retrieved documents."
        ),
        helper_text="Minimum 256 tokens",
        group=ContextManagerGroup.TOKEN_LIMITS,
        validation_schema={"min": 256},
    ),
    SettingDefinition(
        key="context_manager.tokenizer_safety_margin",
        name="Tokenizer safety margin",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.FLOAT,
        default_value=0.90,
        description=(
            "Safety factor applied to the computed input token budget to "
            "compensate for tokenizer mismatch. The system uses the GPT-4 "
            "tokenizer for all models, which can under-count tokens for "
            "non-OpenAI models. A value of 0.90 means 10 percent of the "
            "budget is kept as a safety margin."
        ),
        helper_text="Range 0.5-1.0. Default 0.90 (10% margin).",
        group=ContextManagerGroup.TOKEN_LIMITS,
        validation_schema={"min": 0.5, "max": 1.0},
    ),
    SettingDefinition(
        key="context_manager.max_context_tokens",
        name="Max context tokens",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=3000,
        description=(
            "Token budget for retrieved documents and data within the "
            "context package. If set too low, the AI will not have enough "
            "source material to answer accurately. Ensure this value plus "
            "the system and user token budgets does not exceed the maximum "
            "total tokens."
        ),
        helper_text="Minimum 1 token. Must be less than maximum total tokens.",
        group=ContextManagerGroup.TOKEN_LIMITS,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="context_manager.max_system_tokens",
        name="Max system tokens",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=500,
        description=(
            "Token budget for the system prompt that defines the AI's role, "
            "tone, and constraints. If set too low, the AI might ignore its "
            "formatting instructions or behavioral guidelines. Ensure this "
            "value plus the context and user token budgets does not exceed "
            "the maximum total tokens."
        ),
        helper_text="Minimum 1 token",
        group=ContextManagerGroup.TOKEN_LIMITS,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="context_manager.max_user_tokens",
        name="Max user tokens",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=500,
        description=(
            "Token budget for the user's query and conversation history "
            "within the context package. Longer user messages can be "
            "truncated to fit this limit. Ensure this value plus the system "
            "and context token budgets does not exceed the maximum total tokens."
        ),
        helper_text="Minimum 1 token",
        group=ContextManagerGroup.TOKEN_LIMITS,
        validation_schema={"min": 1},
    ),
    # Context Manager — Retrieval
    SettingDefinition(
        key="context_manager.default_k",
        name="Default K (documents to retrieve)",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=10,
        description=(
            "The number of document chunks to retrieve from the knowledge "
            "base before grounding score filtering. Higher values (for example, 20+) "
            "improve recall but introduce noise that can confuse the LLM and "
            "increase costs. Lower values (for example, 3-5) reduce noise and cost, "
            "but the system might miss relevant information if it is not in "
            "the top results."
        ),
        helper_text="Minimum 1",
        group=ContextManagerGroup.RETRIEVAL,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="context_manager.enable_hybrid_search",
        name="Hybrid search",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.BOOLEAN,
        default_value=True,
        description=(
            "Combines semantic (embedding-based) and lexical (keyword-based) "
            "search for document retrieval. Semantic search finds meaning, "
            "while lexical search finds exact keyword matches. Hybrid search "
            "typically improves result quality by capturing both. When "
            "disabled, only semantic search is used."
        ),
        helper_text="Recommended: enabled",
        group=ContextManagerGroup.RETRIEVAL,
    ),
    SettingDefinition(
        key="context_manager.semantic_weight",
        name="Semantic weight",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.FLOAT,
        default_value=0.7,
        description=(
            "Relative weight given to semantic (embedding-based) search "
            "results when hybrid search is enabled. Increase this weight if "
            "users primarily ask conceptual 'why' or 'how' questions. The "
            "semantic and lexical weights should typically sum to 1.0."
        ),
        helper_text="Range 0.0-1.0. Only applies when hybrid search is enabled.",
        depends_on="context_manager.enable_hybrid_search",
        group=ContextManagerGroup.RETRIEVAL,
        validation_schema={"min": 0.0, "max": 1.0},
    ),
    SettingDefinition(
        key="context_manager.lexical_weight",
        name="Lexical weight",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.FLOAT,
        default_value=0.3,
        description=(
            "Relative weight given to lexical (keyword-based) search results "
            "when hybrid search is enabled. Increase this weight if users "
            "frequently search for specific IDs, error codes, or technical "
            "terms. The semantic and lexical weights should typically sum "
            "to 1.0."
        ),
        helper_text="Range 0.0-1.0. Only applies when hybrid search is enabled.",
        depends_on="context_manager.enable_hybrid_search",
        group=ContextManagerGroup.RETRIEVAL,
        validation_schema={"min": 0.0, "max": 1.0},
    ),
    # Context Manager — Snippets
    SettingDefinition(
        key="context_manager.max_snippets_per_doc",
        name="Max snippets per document",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=3,
        description=(
            "Limits how many text snippets are extracted from each retrieved "
            "document. Lower values prevent any single document from "
            "dominating the context at the expense of other sources. Higher "
            "values provide broader coverage of a document's content but might "
            "crowd out other documents and consume more of the token budget."
        ),
        helper_text="Minimum 1",
        group=ContextManagerGroup.SNIPPETS,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="context_manager.snippet_min_length",
        name="Snippet min length (chars)",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=100,
        description=(
            "Minimum character length for an extracted snippet. Snippets "
            "shorter than this are discarded. Smaller snippets are more "
            "precise but might lack surrounding context needed for the AI to "
            "interpret them correctly."
        ),
        helper_text="Minimum 1 character",
        group=ContextManagerGroup.SNIPPETS,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="context_manager.snippet_max_length",
        name="Snippet max length (chars)",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=500,
        description=(
            "Maximum character length for an extracted snippet. Snippets "
            "exceeding this limit are truncated. Larger snippets provide "
            "more context but consume more of the token budget. Must be "
            "greater than the snippet minimum length."
        ),
        helper_text="Minimum 1 character. Must be greater than snippet min length.",
        group=ContextManagerGroup.SNIPPETS,
        validation_schema={"min": 1},
    ),
    # Context Manager — Context assembly
    SettingDefinition(
        key="context_manager.enforce_hierarchy",
        name="Hierarchical ordering",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.BOOLEAN,
        default_value=True,
        description=(
            "When enabled, context sections are assembled in a fixed order "
            "defined by the priority order setting. LLMs often pay the most "
            "attention to the beginning and end of a prompt, so section "
            "ordering can influence which information the model prioritizes."
        ),
        helper_text="Recommended: enabled",
        group=ContextManagerGroup.CONTEXT_ASSEMBLY,
    ),
    SettingDefinition(
        key="context_manager.priority_order",
        name="Priority order",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.JSON,
        default_value=["system", "context", "user"],
        description=(
            "Defines the ordering of context sections in the assembled "
            "prompt. Sections listed first receive priority when the total "
            "token budget is exceeded. LLMs often pay the most attention to "
            "the beginning and end of a prompt, so the order can influence "
            "response quality. Only applies when hierarchical ordering is "
            "enabled."
        ),
        helper_text='JSON array, for example ["system", "context", "user"]',
        depends_on="context_manager.enforce_hierarchy",
        group=ContextManagerGroup.CONTEXT_ASSEMBLY,
    ),
    SettingDefinition(
        key="context_manager.include_citations",
        name="Include source citations",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.BOOLEAN,
        default_value=True,
        description=(
            "Appends source document references to the assembled context so "
            "the LLM can attribute answers to specific documents. Disabling "
            "saves tokens but removes traceability of generated responses."
        ),
        helper_text="Recommended: enabled for traceability",
        group=ContextManagerGroup.CONTEXT_ASSEMBLY,
    ),
    # Context Manager — Performance
    SettingDefinition(
        key="context_manager.request_timeout_seconds",
        name="Request timeout (seconds)",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=30,
        description=(
            "Maximum wall-clock time for a single context assembly request. "
            "If retrieval and assembly exceed this limit, the request is "
            "cancelled and an error is returned. If you see 504 Gateway "
            "Timeout errors, consider increasing this value."
        ),
        helper_text="Minimum 1 second",
        group=ContextManagerGroup.PERFORMANCE,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="context_manager.max_concurrent_requests",
        name="Max concurrent requests",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=5,
        description=(
            "Limits how many context assembly requests can execute "
            "simultaneously. Protects downstream services from overload. If "
            "you see 429 Too Many Requests errors, consider decreasing this "
            "value to match your database's capacity."
        ),
        helper_text="Minimum 1",
        group=ContextManagerGroup.PERFORMANCE,
        validation_schema={"min": 1},
    ),
    # Context Manager — Compression
    SettingDefinition(
        key="context_manager.compression_mode",
        name="Compression mode",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.STRING,
        default_value="extractive",
        description=(
            "Strategy for reducing context length when it exceeds the token "
            "budget. Extractive mode selects the most relevant sentences "
            "verbatim, which is safer with no hallucination risk. Abstractive "
            "mode uses an LLM to generate a condensed summary, which is more coherent "
            "but requires additional LLM calls and carries a slight "
            "hallucination risk."
        ),
        helper_text="Allowed values: extractive, abstractive",
        group=ContextManagerGroup.COMPRESSION,
        validation_schema={"allowed_values": ["extractive", "abstractive"]},
    ),
    SettingDefinition(
        key="context_manager.compression_loop",
        name="Compression loop",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=3,
        description=(
            "Number of iterative compression passes allowed when the context "
            "still exceeds the token budget after the first pass. Each "
            "additional pass further reduces the content. Set to 0 to "
            "disable iterative compression."
        ),
        helper_text="Minimum 0. Set to 0 to disable retry.",
        group=ContextManagerGroup.COMPRESSION,
        validation_schema={"min": 0},
    ),
    SettingDefinition(
        key="context_manager.compression_temperature",
        name="Compression temperature",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.FLOAT,
        default_value=0.3,
        description=(
            "LLM sampling temperature used during abstractive compression. "
            "Lower values (0.0-0.3) produce more deterministic, faithful "
            "summaries, which is best for factual extraction. Higher values "
            "(0.7-1.0) increase variety but significantly raise the risk of "
            "hallucinations. Only applies when compression mode is set to "
            "abstractive."
        ),
        helper_text="Range 0.0-1.0. Lower is more deterministic.",
        group=ContextManagerGroup.COMPRESSION,
        validation_schema={"min": 0.0, "max": 1.0},
    ),
    SettingDefinition(
        key="context_manager.compression_max_tokens",
        name="Compression max tokens",
        category=SettingCategory.CONTEXT_MANAGER,
        value_type=SettingValueType.INTEGER,
        default_value=2000,
        description=(
            "Token limit for the LLM response during abstractive "
            "compression. Controls the maximum length of the compressed "
            "output. Use a value smaller than the original context to achieve "
            "meaningful reduction."
        ),
        helper_text="Minimum 1 token",
        group=ContextManagerGroup.COMPRESSION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="agentic.max_completion_tokens",
        name="Agentic max completion tokens",
        category=SettingCategory.AI_LLM,
        value_type=SettingValueType.INTEGER,
        default_value=0,
        description=(
            "Optional cap on the number of tokens the LLM may generate in a "
            "single agentic response. Set to 0 (the default) to use the "
            "provider's model-specific default (recommended). Set a positive "
            "value to enforce a hard output-length limit."
        ),
        helper_text="0 = no limit (provider default).",
    ),
    SettingDefinition(
        key="agentic.task_agent_system_prompt",
        name="Task agent system prompt",
        category=SettingCategory.AI_LLM,
        value_type=SettingValueType.STRING,
        default_value=(
            "You are an information assistant for the {product_name} automation system. "
            "Answer user questions concisely and accurately. "
            "Focus on providing helpful, direct answers about tools, services, and capabilities."
        ),
        description=(
            "System prompt prepended to every task agent LLM call. Controls "
            "the agent's persona and behavioral framing. Cannot be blank."
        ),
        helper_text=(
            "Customizes how task agents introduce themselves to the LLM. "
            "Maximum 2000 characters. For structured output requests, "
            "JSON schema instructions are appended after this prompt."
        ),
        validation_schema={"pattern": "\\S[\\s\\S]{0,1999}"},
    ),
    # Workflow Execution — Timeouts
    SettingDefinition(
        key="workflow_engine.max_loop_iterations",
        name="Max loop iterations",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=10000,
        description=(
            "Safety limit that prevents runaway loop execution inside "
            "workflows. If a loop node exceeds this number of iterations, "
            "the workflow engine terminates it and the activity fails."
        ),
        helper_text="Minimum 1",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.script_timeout_seconds",
        name="Script timeout (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=300,
        description=(
            "Maximum execution time for script activities within a workflow. "
            "If a script exceeds this timeout, it is terminated and the "
            "activity fails."
        ),
        helper_text="Minimum 1 second. Default: 300 (5 minutes).",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.script_max_output_kb",
        name="Script max output (KB)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=1024,
        description=(
            "Maximum kilobytes of stdout or stderr captured from a script activity. "
            "This limit applies independently to each stream. Output beyond this "
            "limit is discarded to prevent worker memory exhaustion. The script "
            "continues running until it exits or the timeout fires. "
            "Temporal imposes a 2 MB payload limit per activity result; combined "
            "stdout, stderr, and metadata must stay under this limit."
        ),
        helper_text=(
            "Minimum 256 KB, maximum 2048 KB (2 MB). Default: 1024 KB (1 MB). "
            "This is a per-stream limit; if both stdout and stderr are large, "
            "the combined result may be further truncated to fit Temporal's payload limit."
        ),
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 256, "max": 2048},
    ),
    SettingDefinition(
        key="workflow_engine.agentic_timeout_seconds",
        name="Agentic timeout (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=300,
        description=(
            "Maximum execution time for agentic (AI-driven) activities "
            "within a workflow. Agentic activities involve multi-step LLM "
            "reasoning and can take longer than simple scripts. If exceeded, "
            "the activity is terminated."
        ),
        helper_text="Minimum 1 second. Default: 300 (5 minutes).",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.max_prompt_length",
        name="Max prompt length",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=100000,
        description=(
            "Maximum character length for prompts submitted to agentic "
            "workflow activities. Prevents excessively large inputs from "
            "causing LLM timeouts or excessive costs. Prompts exceeding "
            "this limit are rejected before execution."
        ),
        helper_text="Minimum 1000 characters. Default: 100,000 (100 KB).",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1000},
    ),
    SettingDefinition(
        key="workflow_engine.max_wait_duration_seconds",
        name="Max wait duration (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=2592000,
        description=(
            "Maximum total duration allowed for wait nodes in workflows. "
            "If a wait node's configured duration exceeds this limit, "
            "the activity fails with a ConfigError. Admins can adjust "
            "this value based on organizational requirements."
        ),
        helper_text="Minimum 1 second. Default: 2,592,000 (30 days).",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.aap_timeout_seconds",
        name="AAP timeout (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=3600,
        description=(
            "Maximum execution time for AAP job template and workflow job "
            "template activities within a workflow. If an AAP job exceeds "
            "this timeout, the activity is terminated and fails."
        ),
        helper_text="Minimum 1 second. Default: 3600 (1 hour).",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.approval_decision_window_seconds",
        name="Approval decision window (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=86400,
        description=(
            "Default time window (in seconds) the approver has to respond to an approval request. "
            "Can be overridden per node via the decision_window config field. "
            "If no decision is received within this period, the approval expires."
        ),
        helper_text="Minimum 1 second. Default: 86400 (24 hours).",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.http_request_timeout_seconds",
        name="HTTP request timeout (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=30,
        description=(
            "Maximum execution time for HTTP request activities within a "
            "workflow. If an HTTP request does not complete within this "
            "period, the activity is terminated and fails."
        ),
        helper_text="Minimum 1 second. Default: 30 seconds.",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.converge_wait_duration_seconds",
        name="Converge wait duration (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=86400,
        description=(
            "Default time (in seconds) a converge node waits for incoming branches to arrive. "
            "Can be overridden per node via the wait_duration config field. "
            "When this duration expires, the converge node stops waiting and the workflow "
            "continues according to the node's continue_on_failure setting."
        ),
        helper_text="Minimum 1 second. Default: 86400 (24 hours).",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.continue_on_failure",
        name="Continue on failure (default)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.BOOLEAN,
        default_value=False,
        description=(
            "Default continue-on-failure behavior for all nodes that support "
            "it (executor nodes, loop, converge, approval). When true, "
            "downstream nodes continue executing even if this node fails. "
            "Per-node settings override this default."
        ),
        helper_text="Default: false. Per-node setting takes priority.",
        group=WorkflowEngineGroup.EXECUTION,
    ),
    SettingDefinition(
        key="workflow_engine.retry_max_retries",
        name="Default retry max retries",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=3,
        description=(
            "Default number of retries after the initial attempt for nodes "
            "with retry_policy enabled. 0 disables retries. Applies to "
            "executor and approval nodes when no per-node retry_policy is set."
        ),
        helper_text="Minimum 0. Default: 3.",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 0},
    ),
    SettingDefinition(
        key="workflow_engine.retry_initial_interval",
        name="Default retry initial interval (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=1,
        description=(
            "Default initial wait time in seconds before the first retry. "
            "Subsequent retries scale this up by backoff_coefficient "
            "(exponential) or keep it fixed (fixed backoff)."
        ),
        helper_text="Minimum 1 second. Default: 1 second.",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.retry_max_interval",
        name="Default retry max interval (seconds)",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.INTEGER,
        default_value=60,
        description=(
            "Default maximum wait time in seconds between retries. "
            "Caps the exponential growth so retries never wait longer "
            "than this value regardless of backoff_coefficient."
        ),
        helper_text="Minimum 1 second. Default: 60 seconds.",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="workflow_engine.retry_backoff_coefficient",
        name="Default retry backoff coefficient",
        category=SettingCategory.WORKFLOW_EXECUTION,
        value_type=SettingValueType.FLOAT,
        default_value=2.0,
        description=(
            "Default multiplier applied to the retry interval on each "
            "attempt when using exponential backoff. A coefficient of 2.0 "
            "doubles the wait time each retry until max_interval is reached."
        ),
        helper_text="Minimum 1.0. Default: 2.0.",
        group=WorkflowEngineGroup.EXECUTION,
        validation_schema={"min": 1.0},
    ),
    # Authentication — Local login
    SettingDefinition(
        key="authentication.local_login_enabled",
        name="Local login",
        category=SettingCategory.AUTHENTICATION,
        value_type=SettingValueType.BOOLEAN,
        default_value=True,
        description=(
            "Controls whether non-builtin local users can log in with a "
            "password. When disabled, only built-in accounts (such as admin) "
            "can authenticate with a password. Identity provider users are "
            "not affected by this setting."
        ),
        helper_text=(
            "Disable after configuring identity providers if local user "
            "login is no longer needed. Built-in accounts can always log in."
        ),
        group=AuthenticationGroup.LOCAL_LOGIN,
    ),
    # Application — Document Conversion
    SettingDefinition(
        key="document_conversion.timeout_seconds",
        name="Conversion timeout (seconds)",
        category=SettingCategory.APPLICATION,
        value_type=SettingValueType.INTEGER,
        default_value=30,
        description=(
            "Maximum time allowed for a document conversion operation. If "
            "conversion exceeds this limit, it is cancelled. Large or "
            "complex documents might require a higher value."
        ),
        helper_text="Range 1-300 seconds",
        group=DocumentConversionGroup.GENERAL,
        validation_schema={"min": 1, "max": 300},
    ),
    SettingDefinition(
        key="document_conversion.overwrite_existing",
        name="Overwrite existing files",
        category=SettingCategory.APPLICATION,
        value_type=SettingValueType.BOOLEAN,
        default_value=False,
        description=(
            "Controls whether the system overwrites an existing converted "
            "file if one already exists at the target location. When "
            "disabled, the system skips conversion if the output file is "
            "already present."
        ),
        helper_text="Default: disabled (existing files are preserved)",
        group=DocumentConversionGroup.GENERAL,
    ),
    # Integrations
    SettingDefinition(
        key="integrations.health_check_interval_seconds",
        name="Health check interval",
        category=SettingCategory.INTEGRATIONS,
        value_type=SettingValueType.INTEGER,
        default_value=300,
        description=(
            "Interval in seconds between automatic integration health "
            "checks. Each configured integration is validated on this "
            "schedule to detect connectivity or authentication issues."
        ),
        helper_text="Minimum 60 seconds. Default: 300 (5 minutes).",
        validation_schema={"min": 60},
    ),
    SettingDefinition(
        key="integrations.connection_test_timeout_seconds",
        name="Connection test timeout",
        category=SettingCategory.INTEGRATIONS,
        value_type=SettingValueType.INTEGER,
        default_value=10,
        description=(
            "Maximum time in seconds to wait for an integration "
            "connection test to complete before marking it as failed."
        ),
        helper_text="Minimum 1 second. Default: 10 seconds.",
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="integrations.health_check_batch_size",
        name="Health check batch size",
        category=SettingCategory.INTEGRATIONS,
        value_type=SettingValueType.INTEGER,
        default_value=500,
        description=(
            "Maximum number of integrations validated per health-check "
            "run. Higher values clear the fleet faster but add more load "
            "per run; remaining integrations are picked up on the next run."
        ),
        helper_text="Minimum 1. Default: 500.",
        validation_schema={"min": 1},
    ),
    SettingDefinition(
        key="integrations.discovery_interval_seconds",
        name="Resource discovery interval",
        category=SettingCategory.INTEGRATIONS,
        value_type=SettingValueType.INTEGER,
        default_value=900,
        description=(
            "Interval in seconds between automatic integration resource "
            "discovery runs. Each integration's tools/models are re-discovered "
            "and synced on this schedule so new resources appear without a "
            "manual refresh."
        ),
        helper_text="Minimum 60 seconds. Default: 900 (15 minutes).",
        validation_schema={"min": 60},
    ),
    SettingDefinition(
        key="integrations.discovery_batch_size",
        name="Resource discovery batch size",
        category=SettingCategory.INTEGRATIONS,
        value_type=SettingValueType.INTEGER,
        default_value=500,
        description=(
            "Maximum number of integrations whose resources are re-discovered "
            "per run. Remaining integrations are picked up on the next run."
        ),
        helper_text="Minimum 1. Default: 500.",
        validation_schema={"min": 1},
    ),
    # Rate Limiting
    SettingDefinition(
        key="rate_limiting.requests_per_window",
        name="Requests per window",
        category=SettingCategory.RATE_LIMITING,
        value_type=SettingValueType.INTEGER,
        default_value=0,
        description=(
            "Maximum number of API requests a single user can make within "
            "the configured time window. Set to 0 to disable rate limiting "
            "(default)."
        ),
        helper_text="0 = disabled. Example: 100 requests per 60-second window. Maximum: 10000.",
        validation_schema={"min": 0, "max": 10000},
    ),
    SettingDefinition(
        key="rate_limiting.window_duration_seconds",
        name="Window duration (seconds)",
        category=SettingCategory.RATE_LIMITING,
        value_type=SettingValueType.INTEGER,
        default_value=60,
        description=(
            "Duration of the rate limiting time window in seconds. "
            "The request allowance (above) refills continuously over this "
            "interval using a token bucket algorithm."
        ),
        helper_text="Range: 1-86400 seconds. Default: 60 seconds.",
        validation_schema={"min": 1, "max": 86400},
    ),
    # Service accounts — credential lifetime
    SettingDefinition(
        key="service_accounts.credential_max_lifetime_days",
        name="Credential maximum lifetime (days)",
        category=SettingCategory.AUTHENTICATION,
        value_type=SettingValueType.INTEGER,
        default_value=180,
        description=(
            "Caps how long service account credentials remain valid. When set to a "
            "positive number, any credential created or renewed is forced to expire "
            "within that many days. Set to 0 for no expiry (credentials never expire). "
            "Existing credentials keep their current expiry until they are renewed."
        ),
        helper_text="Days until credentials expire (0 = never). Max 730. Default 180.",
        requires_restart=False,
        validation_schema={"min": 0, "max": 730},
    ),
]
