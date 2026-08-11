"""Constants for field validation and limits across the nexus core module.

This module centralizes all magic numbers and limits used throughout the codebase
to improve maintainability and consistency.
"""

NAME_PATTERN = r"^[a-zA-Z0-9]([a-zA-Z0-9:_-]*[a-zA-Z0-9])?$"
"""Name pattern for projects, policies, and roles.

Must start and end with alphanumeric; middle may contain colons, hyphens,
and underscores.  Single-character names are allowed.
"""


class FieldLimits:
    """Field length and validation limits."""

    # String field limits
    PRINCIPAL_TYPE_MAX_LENGTH = 20
    NAME_MAX_LENGTH = 255
    DESCRIPTION_MAX_LENGTH = 2000
    ERROR_CODE_MAX_LENGTH = 100
    ERROR_MESSAGE_MAX_LENGTH = 500
    PARAMETER_NAME_MAX_LENGTH = 100
    SCHEMA_VERSION_MAX_LENGTH = 50
    TIME_WINDOW_MAX_LENGTH = 50
    NAMESPACED_NAME_MAX_LENGTH = 200

    # List length limits
    APPROVER_LIST_MAX_LENGTH = 1000

    # Pagination limits
    MAX_ITEMS_PER_PAGE = 100

    # Test execution limits
    MAX_PRE_RESOLVED_NODES = 100

    # Cursor and JSON limits for security
    MAX_CURSOR_SIZE = 1024  # 1KB limit for cursor tokens


class WebSocketConfig:
    """WebSocket configuration constants."""

    # Message size limits
    MAX_MESSAGE_SIZE = 1048576  # 1MB

    # Connection limits
    MAX_CONNECTIONS = 100
    MAX_CONNECTIONS_PER_IP = 10

    # Ticket exchange
    TICKET_TTL_SECONDS = 30

    # Health check settings
    CLEANUP_INTERVAL = 30  # seconds - how often to check for stale connections
    ACTIVITY_TIMEOUT = 14400  # seconds (4 hours) - connections idle longer than this are considered stale


class ValidationMessages:
    """Standard validation error messages."""

    LABELS_MUST_BE_DICT = "labels must be a dictionary"
    LABELS_KEY_MUST_BE_STRING = "labels key '{key}' must be a string, got {type_name}"
    LABELS_VALUE_MUST_BE_STRING = "labels value for key '{key}' must be a string, got {type_name}"
    CURSOR_TOO_LARGE = "Cursor too large (max {max_size} bytes)"
    CURSOR_INVALID_FORMAT = "Invalid cursor format: {error}"


class WebhookLimits:
    """Webhook trigger validation limits and defaults."""

    # Webhook path constraints
    PATH_MAX_LENGTH = 128
    PATH_MIN_LENGTH = 1
    PATH_PATTERN = r"^[a-z0-9]([a-z0-9\-_]*[a-z0-9])?$"

    # Payload size limit
    PAYLOAD_MAX_BYTES = 1_048_576  # 1MB


# File upload validation constants
# Minimum file size for reliable MIME type detection (in bytes)
# python-magic requires sufficient bytes to accurately identify file types
MIME_TYPE_DETECTION_MIN_BYTES = 512

# Context data keys for invocation context_data JSONB field
CONTEXT_KEY = "context_data"
# Key for file IDs array in invocation context_data (references FileMetadata table)
CONTEXT_KEY_FILE_IDS = "file_ids"


class RetrieverServiceDefaults:
    """Default values for RetrieverService configuration."""

    # LLM Relevancy Checker Defaults
    LLM_TEMPERATURE = 0.3
    LLM_MAX_TOKENS = 150
    LLM_SIMILARITY_THRESHOLD = 0.7
    LLM_MAX_RESULTS = 10
    LLM_INCLUDE_FILE_METADATA = True
    LLM_USE_TITLE_WEIGHTING = True
    LLM_RECENCY_WEIGHT = 0.1
    LLM_MMR_LAMBDA_PARAM = 0.7
    LLM_MMR_ENABLED = False
    LLM_SYSTEM_PROMPT = (
        "You are a document relevancy scorer. Given a query and document content, "
        "score the relevance from 0.0 to 1.0. Consider semantic meaning, context, "
        "and specific information that answers the query. Return only the numeric score."
    )

    # LLM Ranking Weights (must sum to 1.0)
    LLM_RANKING_CONTENT_SIMILARITY = 0.7
    LLM_RANKING_FILE_METADATA_RELEVANCE = 0.2
    LLM_RANKING_RECENCY = 0.1

    # Keyword Relevancy Checker Defaults
    KEYWORD_SIMILARITY_THRESHOLD = 0.4
    KEYWORD_MAX_RESULTS = 15
    KEYWORD_CASE_SENSITIVE = False
    KEYWORD_STEM_WORDS = True
    KEYWORD_REMOVE_STOPWORDS = True
    KEYWORD_PHRASE_BONUS_MULTIPLIER = 1.5
    KEYWORD_PROXIMITY_SCORING = True
    KEYWORD_FUZZY_MATCHING = False
    KEYWORD_BOOST_TITLE_MATCHES = True
    KEYWORD_BOOST_FILENAME_MATCHES = True
    KEYWORD_PENALTY_FOR_SHORT_DOCUMENTS = False
    KEYWORD_RECENCY_WEIGHT = 0.05
    KEYWORD_MMR_LAMBDA_PARAM = 0.5
    KEYWORD_MMR_ENABLED = False

    # Keyword Processing Constants
    KEYWORD_MINIMUM_STEM_LENGTH = 3
    KEYWORD_MINIMUM_QUERY_WORDS = 2

    # Keyword Ranking Weights (must sum to 1.0)
    KEYWORD_RANKING_TERM_FREQUENCY = 0.4
    KEYWORD_RANKING_FILENAME_MATCH = 0.25
    KEYWORD_RANKING_CONTENT_DENSITY = 0.15
    KEYWORD_RANKING_PROXIMITY_BONUS = 0.05
    KEYWORD_RANKING_EXACT_MATCH_BONUS = 0.1
    KEYWORD_RANKING_FUZZY_MATCH_BONUS = 0.05

    # General Retriever Configuration
    CONTEXT_WINDOW_SIZE = 2000
    DEFAULT_RELEVANCY_SCORE = 0.5  # Default neutral score when relevancy checking fails
    CONCURRENT_RELEVANCY_CHECK_LIMIT = 10  # Maximum concurrent relevancy checks
