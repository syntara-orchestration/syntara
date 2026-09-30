import type { TaskActivity } from '@syntara/contracts'

import { API_EXECUTOR_TYPES, type ApiExecutorType } from '../../../../../constants/executorTypes'

/**
 * Resolved executor strings produced by {@link detectTaskExecutorType} (not API contract values).
 * Use these instead of string literals when comparing `actualExecutor` / `detectedExecutorType`.
 */
export const DetectedExecutorType = {
  /** AAP via connector workaround (ansible connector id), distinct from {@link ExecutorTypeEnum.AAP_JOB_TEMPLATE} */
  AAP: 'aap',
} as const

/**
 * SECURITY: Validates metadata.__executorType against API-only executor types.
 * Uses API_EXECUTOR_TYPES (not VALID_EXECUTOR_TYPES) to prevent untrusted workflow JSON
 * from injecting internal-only types like 'aap' via metadata overrides.
 * The 'aap' type is only set internally by detectAAPConnectorFromPrompt after validation.
 */
function isValidExecutorType(executorType: string | undefined): executorType is ApiExecutorType {
  return executorType !== undefined && API_EXECUTOR_TYPES.has(executorType as ApiExecutorType)
}

// Extended types for internal metadata and non-standard executors
export type TaskActivityWithMetadata = TaskActivity & {
  metadata?: {
    __executorType?: string
  }
  condition?: string
}

export type TaskExecutorTypeDetectionResult = {
  detectedExecutorType: string | undefined
  connectorData: null
  actualExecutor: string
}

/**
 * Checks if a parsed connector object is an AAP connector.
 * SECURITY: Uses hasOwnProperty to check only own properties, preventing prototype pollution.
 */
function isAAPConnector(parsed: unknown): boolean {
  return (
    typeof parsed === 'object' &&
    parsed !== null &&
    Object.prototype.hasOwnProperty.call(parsed, '__type') &&
    (parsed as Record<string, unknown>).__type === 'connector' &&
    Object.prototype.hasOwnProperty.call(parsed, 'connectorId') &&
    (parsed as Record<string, unknown>).connectorId === 'ansible-automation-platform'
  )
}

/**
 * JSON.parse reviver function that strips dangerous keys during parsing.
 * SECURITY: Prevents prototype pollution by rejecting dangerous keys at parse time.
 * More robust than post-parse deletion since it operates during object construction.
 */
function safeJSONReviver(key: string, value: unknown): unknown {
  // Reject dangerous keys that could pollute prototypes
  if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
    return undefined // Skip this property
  }
  return value
}

/**
 * Attempts to detect AAP connector from agentic task's prompt field.
 * Returns DetectedExecutorType.AAP if found, undefined otherwise.
 */
function detectAAPConnectorFromPrompt(data: TaskActivity): string | undefined {
  const prompt = (data as Record<string, unknown>).parameters
    ? ((data as Record<string, unknown>).parameters as Record<string, unknown>).prompt
    : undefined

  if (typeof prompt !== 'string') {
    return undefined
  }

  try {
    // SECURITY: Use reviver function to strip dangerous keys during parsing
    const parsed = JSON.parse(prompt, safeJSONReviver) as unknown

    // SECURITY: Verify parsed result has a clean prototype chain.
    // JSON.parse constructs intermediate objects before the reviver runs,
    // so we confirm the result wasn't somehow assigned a polluted prototype.
    if (typeof parsed === 'object' && parsed !== null && Object.getPrototypeOf(parsed) !== Object.prototype) {
      return undefined
    }

    const isAAP = isAAPConnector(parsed)
    return isAAP ? DetectedExecutorType.AAP : undefined
  } catch {
    // prompt is not JSON — leave as agentic
    return undefined
  }
}

/**
 * Detects the effective executor type for a task Activity.
 * In v2, `activity.type` is the executor directly (e.g. 'script', 'http_request', 'agentic', 'aap_job_template').
 * No more `task.executor` wrapper — the type IS the executor name.
 *
 * For agentic tasks, checks `config.prompt` for a connector payload. If the prompt
 * is a JSON string with `__type: 'connector'` and `connectorId: 'ansible-automation-platform'`,
 * the task is resolved to the internal `aap` executor type so it renders with the AAP icon/label.
 *
 * SECURITY: Validates metadata.__executorType against an allowlist to prevent arbitrary
 * executor type injection from untrusted workflow JSON.
 */
export function detectTaskExecutorType(data: TaskActivity): TaskExecutorTypeDetectionResult {
  const dataWithMetadata = data as TaskActivityWithMetadata
  const metadataExecutorType = dataWithMetadata.metadata?.__executorType

  // SECURITY: Validate metadata override against allowlist
  const validatedOverride = isValidExecutorType(metadataExecutorType) ? metadataExecutorType : undefined

  let resolvedExecutor: string = validatedOverride ?? data.type ?? ''

  // Detect ansible connector inside agentic nodes
  if (!validatedOverride && data.type === 'agentic') {
    const aapExecutor = detectAAPConnectorFromPrompt(data)
    if (aapExecutor) {
      resolvedExecutor = aapExecutor
    }
  }

  return {
    detectedExecutorType: resolvedExecutor,
    connectorData: null,
    actualExecutor: resolvedExecutor,
  }
}
