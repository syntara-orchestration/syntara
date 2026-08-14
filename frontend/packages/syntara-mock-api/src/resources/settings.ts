import type { SettingsAPI } from '@syntara/contracts'

import { mockDate } from './mockDates'

type RuntimeSetting = SettingsAPI['components']['schemas']['RuntimeSettingRead']
type SettingCategory = SettingsAPI['components']['schemas']['SettingCategoryRead']

export const settingsCategories: SettingCategory[] = [
  {
    slug: 'ai_llm',
    name: 'AI / LLM',
    description: 'Artificial intelligence and large language model settings',
    group_names: [],
  },
  {
    slug: 'system',
    name: 'System',
    description: 'System-level settings including observability and diagnostics',
    group_names: ['Observability'],
  },
  {
    slug: 'context_manager',
    name: 'Context Manager',
    description: 'Token limits, retrieval, grounding, compression, and context assembly',
    group_names: [
      'Compression',
      'Context assembly',
      'Grounding scores',
      'Performance',
      'Retrieval',
      'Snippets',
      'Token limits',
    ],
  },
  {
    slug: 'workflow_execution',
    name: 'Workflow Execution',
    description: 'Workflow execution timeouts, duration limits, and input constraints',
    group_names: ['Execution'],
  },
  {
    slug: 'application',
    name: 'Application',
    description: 'Application-level settings including document conversion',
    group_names: ['General'],
  },
  {
    slug: 'authentication',
    name: 'Authentication',
    description: 'Authentication, identity provider, and group sync settings',
    group_names: ['Group mapping', 'Local login'],
  },
]

let nextVersion = 1

function makeSetting(
  overrides: Partial<RuntimeSetting> &
    Pick<RuntimeSetting, 'key' | 'name' | 'category' | 'value_type' | 'default_value'>
): RuntimeSetting {
  const version = nextVersion++
  return {
    id: crypto.randomUUID(),
    description: null,
    helper_text: null,
    depends_on: null,
    group: null,
    value: null,
    effective_value: overrides.default_value,
    requires_restart: false,
    cache_ttl_seconds: null,
    validation_schema: null,
    version,
    created_at: mockDate.daysAgo7,
    updated_at: mockDate.daysAgo1,
    ...overrides,
  }
}

export const settings: RuntimeSetting[] = [
  // ── Context Manager: Compression ────────────────────────────────────────
  makeSetting({
    key: 'context_manager.compression_loop',
    name: 'Compression loop',
    description:
      'Number of iterative compression passes allowed when the context still exceeds the token budget after the first pass. Each additional pass further reduces the content. Set to 0 to disable iterative compression.',
    helper_text: 'Minimum 0. Set to 0 to disable retry.',
    category: 'context_manager',
    group: 'Compression',
    value_type: 'integer',
    default_value: 3,
    validation_schema: { min: 0 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.compression_max_tokens',
    name: 'Compression max tokens',
    description:
      'Token limit for the LLM response during abstractive compression. Controls the maximum length of the compressed output. Use a value smaller than the original context to achieve meaningful reduction.',
    helper_text: 'Minimum 1 token',
    category: 'context_manager',
    group: 'Compression',
    value_type: 'integer',
    default_value: 2000,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.compression_mode',
    name: 'Compression mode',
    description:
      'Strategy for reducing context length when it exceeds the token budget. Extractive mode selects the most relevant sentences verbatim, which is safer with no hallucination risk. Abstractive mode uses an LLM to generate a condensed summary, which is more coherent but requires additional LLM calls and carries a slight hallucination risk.',
    helper_text: 'Allowed values: extractive, abstractive',
    category: 'context_manager',
    group: 'Compression',
    value_type: 'string',
    default_value: 'extractive',
    validation_schema: { allowed_values: ['extractive', 'abstractive'] } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.compression_temperature',
    name: 'Compression temperature',
    description:
      'LLM sampling temperature used during abstractive compression. Lower values (0.0-0.3) produce more deterministic, faithful summaries, which is best for factual extraction. Higher values (0.7-1.0) increase variety but significantly raise the risk of hallucinations. Only applies when compression mode is set to abstractive.',
    helper_text: 'Range 0.0-1.0. Lower is more deterministic.',
    category: 'context_manager',
    group: 'Compression',
    value_type: 'float',
    default_value: 0.3,
    validation_schema: { min: 0, max: 1 } as unknown as Record<string, never>,
  }),

  // ── Context Manager: Context assembly ───────────────────────────────────
  makeSetting({
    key: 'context_manager.enforce_hierarchy',
    name: 'Hierarchical ordering',
    description:
      'When enabled, context sections are assembled in a fixed order defined by the priority order setting. LLMs often pay the most attention to the beginning and end of a prompt, so section ordering can influence which information the model prioritizes.',
    helper_text: 'Recommended: enabled',
    category: 'context_manager',
    group: 'Context assembly',
    value_type: 'boolean',
    default_value: true,
  }),
  makeSetting({
    key: 'context_manager.include_citations',
    name: 'Include source citations',
    description:
      'Appends source document references to the assembled context so the LLM can attribute answers to specific documents. Disabling saves tokens but removes traceability of generated responses.',
    helper_text: 'Recommended: enabled for traceability',
    category: 'context_manager',
    group: 'Context assembly',
    value_type: 'boolean',
    default_value: true,
  }),
  makeSetting({
    key: 'context_manager.priority_order',
    name: 'Priority order',
    description:
      'Defines the ordering of context sections in the assembled prompt. Sections listed first receive priority when the total token budget is exceeded. LLMs often pay the most attention to the beginning and end of a prompt, so the order can influence response quality. Only applies when hierarchical ordering is enabled.',
    helper_text: 'JSON array, for example ["system", "context", "user"]',
    depends_on: 'context_manager.enforce_hierarchy',
    category: 'context_manager',
    group: 'Context assembly',
    value_type: 'json',
    default_value: ['system', 'context', 'user'],
  }),

  // ── Context Manager: Grounding scores ───────────────────────────────────
  makeSetting({
    key: 'context_manager.minimum_grounding_score',
    name: 'Minimum grounding score',
    description:
      'The lowest acceptable confidence score for considering a retrieved document. Documents between this value and the required score are included but ranked lower. A lower threshold ensures the user gets an answer more often but increases the risk of unfounded claims.',
    helper_text: 'Range 0.0-1.0. Must be less than or equal to required grounding score.',
    category: 'context_manager',
    group: 'Grounding scores',
    value_type: 'float',
    default_value: 0.5,
    validation_schema: { min: 0, max: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.required_grounding_score',
    name: 'Required grounding score',
    description:
      'The minimum confidence score a retrieved document must achieve to be included in the context. Documents below this threshold are excluded entirely. A higher threshold increases accuracy and reduces hallucinations, but if set too high the system can refuse to answer valid questions because the retrieval confidence is not high enough. A lower threshold ensures answers more often but increases the risk of unfounded claims.',
    helper_text: 'Range 0.0-1.0',
    category: 'context_manager',
    group: 'Grounding scores',
    value_type: 'float',
    default_value: 0.7,
    validation_schema: { min: 0, max: 1 } as unknown as Record<string, never>,
  }),

  // ── Context Manager: Performance ────────────────────────────────────────
  makeSetting({
    key: 'context_manager.max_concurrent_requests',
    name: 'Max concurrent requests',
    description:
      "Limits how many context assembly requests can execute simultaneously. Protects downstream services from overload. If you see 429 Too Many Requests errors, consider decreasing this value to match your database's capacity.",
    helper_text: 'Minimum 1',
    category: 'context_manager',
    group: 'Performance',
    value_type: 'integer',
    default_value: 5,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.request_timeout_seconds',
    name: 'Request timeout (seconds)',
    description:
      'Maximum wall-clock time for a single context assembly request. If retrieval and assembly exceed this limit, the request is cancelled and an error is returned. If you see 504 Gateway Timeout errors, consider increasing this value.',
    helper_text: 'Minimum 1 second',
    category: 'context_manager',
    group: 'Performance',
    value_type: 'integer',
    default_value: 30,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),

  // ── Context Manager: Retrieval ──────────────────────────────────────────
  makeSetting({
    key: 'context_manager.default_k',
    name: 'Default K (documents to retrieve)',
    description:
      'The number of document chunks to retrieve from the knowledge base before grounding score filtering. Higher values (for example, 20+) improve recall but introduce noise that can confuse the LLM and increase costs. Lower values (for example, 3-5) reduce noise and cost, but the system might miss relevant information if it is not in the top results.',
    helper_text: 'Minimum 1',
    category: 'context_manager',
    group: 'Retrieval',
    value_type: 'integer',
    default_value: 10,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.enable_hybrid_search',
    name: 'Hybrid search',
    description:
      'Combines semantic (embedding-based) and lexical (keyword-based) search for document retrieval. Semantic search finds meaning, while lexical search finds exact keyword matches. Hybrid search typically improves result quality by capturing both. When disabled, only semantic search is used.',
    helper_text: 'Recommended: enabled',
    category: 'context_manager',
    group: 'Retrieval',
    value_type: 'boolean',
    default_value: true,
  }),
  makeSetting({
    key: 'context_manager.lexical_weight',
    name: 'Lexical weight',
    description:
      'Relative weight given to lexical (keyword-based) search results when hybrid search is enabled. Increase this weight if users frequently search for specific IDs, error codes, or technical terms. The semantic and lexical weights should typically sum to 1.0.',
    helper_text: 'Range 0.0-1.0. Only applies when hybrid search is enabled.',
    depends_on: 'context_manager.enable_hybrid_search',
    category: 'context_manager',
    group: 'Retrieval',
    value_type: 'float',
    default_value: 0.3,
    validation_schema: { min: 0, max: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.semantic_weight',
    name: 'Semantic weight',
    description:
      "Relative weight given to semantic (embedding-based) search results when hybrid search is enabled. Increase this weight if users primarily ask conceptual 'why' or 'how' questions. The semantic and lexical weights should typically sum to 1.0.",
    helper_text: 'Range 0.0-1.0. Only applies when hybrid search is enabled.',
    depends_on: 'context_manager.enable_hybrid_search',
    category: 'context_manager',
    group: 'Retrieval',
    value_type: 'float',
    default_value: 0.7,
    validation_schema: { min: 0, max: 1 } as unknown as Record<string, never>,
  }),

  // ── Context Manager: Snippets ───────────────────────────────────────────
  makeSetting({
    key: 'context_manager.max_snippets_per_doc',
    name: 'Max snippets per document',
    description:
      "Limits how many text snippets are extracted from each retrieved document. Lower values prevent any single document from dominating the context at the expense of other sources. Higher values provide broader coverage of a document's content but might crowd out other documents and consume more of the token budget.",
    helper_text: 'Minimum 1',
    category: 'context_manager',
    group: 'Snippets',
    value_type: 'integer',
    default_value: 3,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.snippet_max_length',
    name: 'Snippet max length (chars)',
    description:
      'Maximum character length for an extracted snippet. Snippets exceeding this limit are truncated. Larger snippets provide more context but consume more of the token budget. Must be greater than the snippet minimum length.',
    helper_text: 'Minimum 1 character. Must be greater than snippet min length.',
    category: 'context_manager',
    group: 'Snippets',
    value_type: 'integer',
    default_value: 500,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.snippet_min_length',
    name: 'Snippet min length (chars)',
    description:
      'Minimum character length for an extracted snippet. Snippets shorter than this are discarded. Smaller snippets are more precise but might lack surrounding context needed for the AI to interpret them correctly.',
    helper_text: 'Minimum 1 character',
    category: 'context_manager',
    group: 'Snippets',
    value_type: 'integer',
    default_value: 100,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),

  // ── Context Manager: Token limits ───────────────────────────────────────
  makeSetting({
    key: 'context_manager.max_context_tokens',
    name: 'Max context tokens',
    description:
      'Token budget for retrieved documents and data within the context package. If set too low, the AI will not have enough source material to answer accurately. Ensure this value plus the system and user token budgets does not exceed the maximum total tokens.',
    helper_text: 'Minimum 1 token. Must be less than maximum total tokens.',
    category: 'context_manager',
    group: 'Token limits',
    value_type: 'integer',
    default_value: 3000,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.max_system_tokens',
    name: 'Max system tokens',
    description:
      "Token budget for the system prompt that defines the AI's role, tone, and constraints. If set too low, the AI might ignore its formatting instructions or behavioral guidelines. Ensure this value plus the context and user token budgets does not exceed the maximum total tokens.",
    helper_text: 'Minimum 1 token',
    category: 'context_manager',
    group: 'Token limits',
    value_type: 'integer',
    default_value: 500,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.max_total_tokens',
    name: 'Max total tokens',
    description:
      'The maximum number of tokens for the entire prompt sent to the LLM, including system, context, and user sections. Higher values allow more documents and detailed instructions but increase latency and cost. Lower values are faster and cheaper, but the model can lose context or miss key facts because they were truncated.',
    helper_text: 'Minimum 1 token',
    category: 'context_manager',
    group: 'Token limits',
    value_type: 'integer',
    default_value: 4000,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'context_manager.max_user_tokens',
    name: 'Max user tokens',
    description:
      "Token budget for the user's query and conversation history within the context package. Longer user messages can be truncated to fit this limit. Ensure this value plus the system and context token budgets does not exceed the maximum total tokens.",
    helper_text: 'Minimum 1 token',
    category: 'context_manager',
    group: 'Token limits',
    value_type: 'integer',
    default_value: 500,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),

  // ── System ──────────────────────────────────────────────────────────────
  makeSetting({
    key: 'logging.log_level',
    name: 'System Log Level',
    description:
      'Determines how much detail the system records. Changes are applied dynamically without a restart. Logging levels follow a hierarchical threshold. When you set a level, the application records everything at that level and above. INFO or WARNING is standard for production. Use DEBUG only during troubleshooting, as it creates large volumes of data and can slow down the application.',
    helper_text: 'One of: DEBUG, INFO, WARNING, ERROR, CRITICAL',
    category: 'system',
    value_type: 'string',
    default_value: 'INFO',
    validation_schema: {
      allowed_values: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
    } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'metrics.perf_test_mode',
    name: 'Performance test mode',
    description:
      'Activates the in-memory metrics store and exposes internal metrics endpoints for performance testing. Raw metric records are stored in memory and queryable without restarting the application. Running heavy loads can cause high memory usage. This mode is designed for short-term testing in non-production environments, not continuous operation.',
    helper_text: 'Enable only in non-production environments',
    category: 'system',
    group: 'Observability',
    value_type: 'boolean',
    default_value: false,
  }),
  makeSetting({
    key: 'agentic.max_completion_tokens',
    name: 'Agentic max completion tokens',
    description:
      "Optional cap on the number of tokens the LLM may generate in a single agentic response. Set to 0 (the default) to use the provider's model-specific default (recommended). Set a positive value to enforce a hard output-length limit.",
    helper_text: '0 = no limit (provider default).',
    category: 'ai_llm',
    value_type: 'integer',
    default_value: 0,
  }),

  // ── Workflow Execution ─────────────────────────────────────────────────
  makeSetting({
    key: 'workflow_engine.max_loop_iterations',
    name: 'Max loop iterations',
    description:
      'Safety limit that prevents runaway loop execution inside workflows. If a loop node exceeds this number of iterations, the workflow engine terminates it and the workflow fails.',
    helper_text: 'Minimum 1',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 10000,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.script_timeout_seconds',
    name: 'Script timeout (seconds)',
    description:
      'Maximum execution time for script activities within a workflow. If a script exceeds this timeout, it is terminated and the activity fails.',
    helper_text: 'Minimum 1 second. Default: 300 (5 minutes).',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 300,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.agentic_timeout_seconds',
    name: 'Agentic timeout (seconds)',
    description:
      'Maximum execution time for agentic (AI-driven) activities within a workflow. Agentic activities involve multi-step LLM reasoning and can take longer than simple scripts. If exceeded, the activity is terminated.',
    helper_text: 'Minimum 1 second. Default: 300 (5 minutes).',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 300,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.max_prompt_length',
    name: 'Max prompt length',
    description:
      'Maximum character length for prompts submitted to agentic workflow activities. Prevents excessively large inputs from causing LLM timeouts or excessive costs. Prompts exceeding this limit are rejected before execution.',
    helper_text: 'Minimum 1000 characters. Default: 100,000 (100 KB).',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 100000,
    validation_schema: { min: 1000 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.max_wait_duration_seconds',
    name: 'Max wait duration (seconds)',
    description:
      "Maximum total duration allowed for wait nodes in workflows. If a wait node's configured duration exceeds this limit, the activity fails with a configuration error.",
    helper_text: 'Minimum 1 second. Default: 2,592,000 (30 days).',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 2592000,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.aap_timeout_seconds',
    name: 'AAP timeout (seconds)',
    description:
      'Maximum execution time for AAP job template and workflow template activities. If the AAP job exceeds this timeout, the activity fails.',
    helper_text: 'Minimum 1 second. Default: 3600 (1 hour).',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 3600,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.approval_decision_window_seconds',
    name: 'Approval decision window (seconds)',
    description:
      'Maximum time the workflow engine waits for an approval activity to complete. If no response is received within this period, the approval activity times out.',
    helper_text: 'Minimum 1 second. Default: 86400 (24 hours).',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 86400,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.converge_wait_duration_seconds',
    name: 'Converge wait duration (seconds)',
    description:
      'Default time a converge node waits for incoming branches. Can be overridden per node via wait_duration config field.',
    helper_text: 'Minimum 1 second. Default: 86400 (24 hours).',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 86400,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.http_request_timeout_seconds',
    name: 'HTTP request timeout (seconds)',
    description:
      'Maximum execution time for HTTP request activities. If the request does not complete within this time, the activity fails.',
    helper_text: 'Minimum 1 second. Default: 30.',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'integer',
    default_value: 30,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.continue_on_failure',
    name: 'Default continue on failure',
    description:
      'System-wide default for continue-on-failure behavior. When enabled, downstream nodes continue executing even if an upstream node fails. Individual nodes can override this setting.',
    helper_text: 'Applies to all node types that support continue-on-failure.',
    category: 'workflow_execution',
    group: 'Execution',
    value_type: 'boolean',
    default_value: false,
  }),
  makeSetting({
    key: 'workflow_engine.retry_max_retries',
    name: 'Default max retries',
    description:
      'Default number of retry attempts after a node failure. 0 disables retry. Individual nodes can override this setting.',
    helper_text: 'Minimum 0. Default: 3.',
    category: 'workflow_execution',
    group: 'Retry policy',
    value_type: 'integer',
    default_value: 3,
    validation_schema: { min: 0 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.retry_initial_interval',
    name: 'Default retry initial interval (seconds)',
    description: 'Default initial wait time before the first retry attempt.',
    helper_text: 'Minimum 1 second. Default: 1.',
    category: 'workflow_execution',
    group: 'Retry policy',
    value_type: 'integer',
    default_value: 1,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.retry_max_interval',
    name: 'Default retry max interval (seconds)',
    description: 'Maximum wait time between retry attempts when using exponential backoff.',
    helper_text: 'Minimum 1 second. Default: 60.',
    category: 'workflow_execution',
    group: 'Retry policy',
    value_type: 'integer',
    default_value: 60,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'workflow_engine.retry_backoff_coefficient',
    name: 'Default retry backoff coefficient',
    description: 'Multiplier applied to the retry interval on each attempt when using exponential backoff.',
    helper_text: 'Minimum 1.0. Default: 2.0.',
    category: 'workflow_execution',
    group: 'Retry policy',
    value_type: 'float',
    default_value: 2.0,
    validation_schema: { min: 1 } as unknown as Record<string, never>,
  }),

  // ── Authentication ─────────────────────────────────────────────────────
  makeSetting({
    key: 'authentication.local_login_enabled',
    name: 'Local login',
    description:
      'Controls whether non-builtin local users can log in with a password. When disabled, only built-in accounts (such as admin) can authenticate with a password. Identity provider users are not affected by this setting.',
    helper_text:
      'Disable after configuring identity providers if local user login is no longer needed. Built-in accounts can always log in.',
    category: 'authentication',
    group: 'Local login',
    value_type: 'boolean',
    default_value: true,
  }),

  // ── Application: Document Conversion ───────────────────────────────────
  makeSetting({
    key: 'document_conversion.timeout_seconds',
    name: 'Conversion timeout (seconds)',
    description:
      'Maximum time allowed for a document conversion operation. If conversion exceeds this limit, it is cancelled. Large or complex documents might require a higher value.',
    helper_text: 'Range 1-300 seconds',
    category: 'application',
    group: 'General',
    value_type: 'integer',
    default_value: 30,
    validation_schema: { min: 1, max: 300 } as unknown as Record<string, never>,
  }),
  makeSetting({
    key: 'document_conversion.overwrite_existing',
    name: 'Overwrite existing files',
    description:
      'Controls whether the system overwrites an existing converted file if one already exists at the target location. When disabled, the system skips conversion if the output file is already present.',
    helper_text: 'Default: disabled (existing files are preserved)',
    category: 'application',
    group: 'General',
    value_type: 'boolean',
    default_value: false,
  }),
]
