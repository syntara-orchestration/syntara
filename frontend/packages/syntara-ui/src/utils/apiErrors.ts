/**
 * API Error Parsing Utilities
 *
 * Provides consistent error parsing for RFC 9457 Problem Details format including:
 * - RFC 9457 Problem Details: { type: "...", title: "...", detail: "...", code: "...", retryable: boolean }
 * - FastAPI validation errors: { detail: [...] }
 * - openapi-fetch wrapped errors: { cause: { ... }, response: { status: ... } }
 * - WebSocket error events: { data: { ... } }
 */

/** RFC 9457 Problem Details format */
export type ProblemDetails = {
  type: string
  title: string
  detail: string
  instance?: string | null
  status?: number
  code: string
  retryable: boolean
}

/** Error codes returned by the API (RFC 9457 codes) */
export type ApiErrorCode =
  // Workflow errors
  | 'WORKFLOW_NAME_CONFLICT'
  | 'WORKFLOW_DISABLED'
  | 'WORKFLOW_NOT_FOUND'
  | 'WORKFLOW_VERSION_NOT_FOUND'
  | 'WORKFLOW_DEFINITION_INVALID'
  // Provider/Tool errors
  | 'PROVIDER_NAME_CONFLICT'
  | 'PROVIDER_NOT_FOUND'
  | 'TOOL_NOT_FOUND'
  | 'TOOL_VALIDATION_ERROR'
  // Validation errors
  | 'VALIDATION_ERROR'
  | 'FILE_VALIDATION_ERROR'
  | 'FILE_TOO_LARGE'
  | 'UNSUPPORTED_FILE_FORMAT'
  | 'TOO_MANY_FILES'
  // Settings errors
  | 'VERSION_CONFLICT'
  | 'SETTING_NOT_FOUND'
  | 'SETTING_VERSION_CONFLICT'
  | 'SETTING_VALIDATION_ERROR'
  // Auth errors
  | 'AUTHENTICATION_REQUIRED'
  | 'REQUEST_VALIDATION_ERROR'
  // System errors
  | 'LLM_CONFIGURATION_ERROR'
  | 'TEMPORAL_UNAVAILABLE'
  | 'EXECUTION_NOT_FOUND'
  | 'INTERNAL_ERROR'

/** API error format (RFC 9457 + wrappers) */
export type ApiError = {
  // RFC 9457 Problem Details fields
  type?: string
  title?: string
  detail?: unknown // Can be string (RFC 9457) or array (FastAPI validation)
  instance?: string | null
  code?: string
  retryable?: boolean
  status?: number
  statusCode?: number

  // Wrapper fields
  data?: unknown // WebSocket/envelope wrappers
  response?: { status?: number; statusText?: string } // openapi-fetch
  cause?: {
    message?: string
    error?: string
    status?: number
    code?: string
    title?: string
    detail?: unknown
    retryable?: boolean
  } // openapi-fetch nested
}

export type ApiValidationFieldError = {
  /** Dot-delimited field path (react-hook-form compatible), e.g. "configuration.api_key" */
  field: string
  message: string
}

/** Max length before stripping tags (cap work and memory on hostile input). */
const USER_ERROR_PROCESSING_MAX = 50_000
/** Max length shown in UI after sanitization. */
const USER_ERROR_DISPLAY_MAX = 2000

/**
 * Removes each substring that starts with `'<'` and ends at the next `'>'` (same as the old
 * `/<[^>]*>/g` replace), in **O(n)** time with no regex backtracking.
 * Unmatched `'<'` (no closing `'>'`) is kept verbatim.
 */
function stripAngleBracketSegmentsLinear(s: string): string {
  const parts: string[] = []
  let i = 0
  const n = s.length
  while (i < n) {
    const lt = s.indexOf('<', i)
    if (lt === -1) {
      parts.push(s.slice(i))
      break
    }
    parts.push(s.slice(i, lt))
    const gt = s.indexOf('>', lt + 1)
    if (gt === -1) {
      parts.push(s.slice(lt))
      break
    }
    i = gt + 1
  }
  return parts.join('')
}

/**
 * Normalizes server/API text for display in alerts and descriptions: strips HTML-like tags,
 * removes NULs, and caps length so hostile or oversized payloads cannot dominate the UI.
 * React text nodes escape HTML, but this is defense-in-depth for any consumer or future markup.
 */
export function sanitizeUserFacingErrorText(message: string): string {
  if (!message) {
    return message
  }
  let s = message.length > USER_ERROR_PROCESSING_MAX ? message.slice(0, USER_ERROR_PROCESSING_MAX) : message
  s = stripAngleBracketSegmentsLinear(s)
  s = s.replaceAll('\u0000', '')
  if (s.length > USER_ERROR_DISPLAY_MAX) {
    return `${s.slice(0, USER_ERROR_DISPLAY_MAX - 1)}…`
  }
  return s
}

function finalizeUserFacingMessage(message: string): string {
  return sanitizeUserFacingErrorText(message)
}

/**
 * Extracts an HTTP status code from various error formats (including openapi-fetch wrapped errors).
 *
 * @param error - The error object to extract status from
 * @returns HTTP status code if available
 */
function extractNumericStatus(obj: Record<string, unknown>): number | undefined {
  if (typeof obj.status === 'number') return obj.status
  if (typeof obj.statusCode === 'number') return obj.statusCode
  return undefined
}

export function getErrorStatus(error: unknown): number | undefined {
  if (!error || typeof error !== 'object') {
    return undefined
  }

  const err = error as ApiError

  const direct = extractNumericStatus(err as unknown as Record<string, unknown>)
  if (direct !== undefined) return direct

  // openapi-fetch/openapi-react-query stores status in response.status
  if (err.response && typeof err.response === 'object') {
    const responseStatus = extractNumericStatus(err.response as Record<string, unknown>)
    if (responseStatus !== undefined) return responseStatus
  }

  // openapi-fetch nested cause wrapper
  if (err.cause && typeof err.cause === 'object') {
    const causeStatus = extractNumericStatus(err.cause as Record<string, unknown>)
    if (causeStatus !== undefined) return causeStatus
  }

  // Some wrappers store the response body under `data` (which may include status fields)
  if (err.data && typeof err.data === 'object') {
    const dataStatus = extractNumericStatus(err.data as Record<string, unknown>)
    if (dataStatus !== undefined) return dataStatus
  }

  return undefined
}

/**
 * Detects if an error is a 503 Service Unavailable error.
 *
 * Checks for:
 * - HTTP status code 503
 * - RFC 9457 error codes: LLM_CONFIGURATION_ERROR, TEMPORAL_UNAVAILABLE
 *
 * @param error - The error object to check
 * @returns true if the error is a 503 Service Unavailable error
 *
 * @example
 * if (isServiceUnavailableError(error)) {
 *   return <EmptyStateServiceUnavailable description={getErrorMessage(error)} />
 * }
 */
export function isServiceUnavailableError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false
  }

  // Check status code
  if (getErrorStatus(error) === 503) {
    return true
  }

  // Check RFC 9457 error codes
  const code = getErrorCode(error)
  if (code === 'LLM_CONFIGURATION_ERROR' || code === 'TEMPORAL_UNAVAILABLE') {
    return true
  }

  return false
}

/**
 * Detects if an error is a 403 Forbidden / authorization error.
 *
 * Checks status code first, then falls back to message/code heuristics
 * because openapi-react-query errors may not carry the HTTP status.
 */
export function isForbiddenError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false
  }

  if (getErrorStatus(error) === 403) {
    return true
  }

  const code = getErrorCode(error)
  if (code === 'FORBIDDEN' || code === 'AUTHORIZATION_ERROR' || code === 'AUTHORIZATION_DENIED') {
    return true
  }

  const message = getErrorMessage(error).toLowerCase()
  if (message.includes('not authorized') || message.includes('forbidden')) {
    return true
  }

  return false
}

/**
 * Extracts a user-friendly message from RFC 9457 error formats.
 *
 * Tries to extract message from (in order):
 * 1. error.detail (RFC 9457 detail field - string)
 * 2. error.detail (FastAPI validation array)
 * 3. error.title (RFC 9457 title as fallback)
 * 4. Wrapped errors (data, cause)
 * 5. Falls back to "An unexpected error occurred"
 *
 * @param error - The error object to extract message from
 * @returns A user-friendly error message
 *
 * @example
 * const message = getErrorMessage(error)
 * showAlert({ title: 'Error', message })
 */
export function getErrorMessage(error: unknown): string {
  const fallback = 'An unexpected error occurred'

  if (!error) {
    return finalizeUserFacingMessage(fallback)
  }

  if (typeof error === 'string') {
    return finalizeUserFacingMessage(error)
  }

  if (typeof error !== 'object') {
    return finalizeUserFacingMessage(fallback)
  }

  // Handle native Error instances
  if (error instanceof Error && typeof error.message === 'string' && error.message) {
    return finalizeUserFacingMessage(error.message)
  }

  return finalizeUserFacingMessage(extractErrorMessage(error, fallback, new WeakSet<object>()))
}

/** Extracts the first non-empty string message from an object's msg/message/detail fields. */
function extractItemMessage(item: { msg?: unknown; message?: unknown; detail?: unknown }): string | null {
  return (
    (typeof item.msg === 'string' && item.msg) ||
    (typeof item.message === 'string' && item.message) ||
    (typeof item.detail === 'string' && item.detail) ||
    null
  )
}

const LOC_CONTEXT_TOKENS = new Set(['body', 'query', 'path', 'header'])

/** Parses FastAPI `loc` array into a dot-separated field path, stripping common context tokens. */
function parseLocPath(loc: unknown[]): string | null {
  const parts = loc
    .map((p) => (typeof p === 'string' || typeof p === 'number' ? String(p) : null))
    .filter((p): p is string => !!p)
    .filter((p) => !LOC_CONTEXT_TOKENS.has(p))
  return parts.length > 0 ? parts.join('.') : null
}

/** Formats a single FastAPI validation detail item into a displayable string. */
function formatValidationItem(item: unknown): string | null {
  if (!item) return null
  if (typeof item === 'string') return item
  if (typeof item !== 'object') return null

  const it = item as { msg?: unknown; message?: unknown; detail?: unknown; loc?: unknown }
  const message = extractItemMessage(it)
  if (!message) return null

  if (Array.isArray(it.loc) && it.loc.length > 0) {
    const fieldPath = parseLocPath(it.loc)
    if (fieldPath) return `${fieldPath}: ${message}`
  }

  return message
}

/** Formats an array of FastAPI validation detail items into a summary string. */
function formatValidationDetailArray(detail: unknown[]): string | null {
  const msgs = detail.map(formatValidationItem).filter((m): m is string => !!m)
  if (msgs.length === 0) return null
  return msgs.slice(0, 3).join('; ') + (msgs.length > 3 ? ` (+${msgs.length - 3} more)` : '')
}

/** Extracts direct string fields from an error object (detail, message, title). */
function extractDirectMessage(err: ApiError): string | null {
  if (typeof err.detail === 'string' && err.detail) return err.detail
  if (Array.isArray(err.detail)) {
    const formatted = formatValidationDetailArray(err.detail)
    if (formatted) return formatted
  }
  const msg = (err as unknown as Record<string, unknown>).message
  if (typeof msg === 'string' && msg) return msg
  if (typeof err.title === 'string' && err.title) return err.title
  return null
}

/** Recursively unwraps nested error wrappers (data, cause) looking for a message. */
function unwrapNestedMessage(err: ApiError, fallback: string, visited: WeakSet<object>): string | null {
  if (err.data && typeof err.data === 'object') {
    const dataMessage = extractErrorMessage(err.data, fallback, visited)
    if (dataMessage !== fallback) return dataMessage
  }
  if (err.cause && typeof err.cause === 'object') {
    const causeMessage = extractErrorMessage(err.cause, fallback, visited)
    if (causeMessage !== fallback) return causeMessage
  }
  return null
}

function extractErrorMessage(value: unknown, fallback: string, visited: WeakSet<object>): string {
  if (!value) return fallback
  if (typeof value === 'string') return value
  if (typeof value !== 'object') return fallback
  if (value instanceof Error && typeof value.message === 'string' && value.message) return value.message

  if (visited.has(value)) return fallback
  visited.add(value)

  const err = value as ApiError

  const direct = extractDirectMessage(err)
  if (direct) return direct

  return unwrapNestedMessage(err, fallback, visited) ?? fallback
}

function toUnknownArray(value: unknown): unknown[] | undefined {
  return Array.isArray(value) ? (value as unknown[]) : undefined
}

function extractValidationDetailArray(error: unknown): unknown[] | undefined {
  if (!error || typeof error !== 'object') return undefined

  const err = error as ApiError

  const directDetail = toUnknownArray(err.detail)
  if (directDetail) return directDetail

  // openapi-fetch often wraps response body in `cause`
  if (err.cause && typeof err.cause === 'object') {
    const cause = err.cause as { detail?: unknown }
    const causeDetail = toUnknownArray(cause.detail)
    if (causeDetail) return causeDetail
  }

  // Some wrappers/envelopes store the body under `data`
  if (err.data && typeof err.data === 'object') {
    const data = err.data as { detail?: unknown }
    const dataDetail = toUnknownArray(data.detail)
    if (dataDetail) return dataDetail
  }

  // nested detail object may contain its own detail array
  if (err.detail && typeof err.detail === 'object') {
    const nested = err.detail as { detail?: unknown }
    const nestedDetail = toUnknownArray(nested.detail)
    if (nestedDetail) return nestedDetail
  }

  return undefined
}

/**
 * Detects if an error is a validation error.
 *
 * Checks for:
 * - HTTP status code 422
 * - RFC 9457 validation error codes (VALIDATION_ERROR, FILE_VALIDATION_ERROR, TOOL_VALIDATION_ERROR)
 * - FastAPI validation error format (detail array)
 *
 * @param error - The error object to check
 * @returns true if the error is a validation error
 *
 * @example
 * if (isValidationError(error)) {
 *   // Keep alert visible until user dismisses it
 * }
 */
export function isValidationError(error: unknown): boolean {
  // Check for 422 status code
  if (getErrorStatus(error) === 422) {
    return true
  }

  // Check for RFC 9457 validation error codes
  const code = getErrorCode(error)
  if (code === 'VALIDATION_ERROR' || code === 'FILE_VALIDATION_ERROR' || code === 'TOOL_VALIDATION_ERROR') {
    return true
  }

  // Check for FastAPI validation error format (detail array)
  const detailArray = extractValidationDetailArray(error)
  return detailArray !== undefined
}

/**
 * Extracts field-level validation errors from FastAPI/OpenAPI error formats.
 *
 * Intended for mapping backend validation errors onto react-hook-form fields.
 */
export function getValidationFieldErrors(error: unknown): ApiValidationFieldError[] {
  const detail = extractValidationDetailArray(error)
  if (!detail) return []

  const out: ApiValidationFieldError[] = []
  for (const item of detail) {
    if (!item || typeof item !== 'object') continue

    const it = item as { msg?: unknown; message?: unknown; detail?: unknown; loc?: unknown }
    const message = extractItemMessage(it)
    if (!message) continue

    if (!Array.isArray(it.loc) || it.loc.length === 0) continue

    const field = parseLocPath(it.loc)
    if (!field) continue

    out.push({ field, message: finalizeUserFacingMessage(message) })
  }

  return out
}

/**
 * Extracts the RFC 9457 error code from an API error.
 *
 * @param error - The error object
 * @returns The error code or undefined if not found
 *
 * @example
 * const code = getErrorCode(error)
 * if (code === 'LLM_CONFIGURATION_ERROR') {
 *   // Handle configuration error
 * }
 */
export function getErrorCode(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') {
    return undefined
  }

  const err = error as ApiError

  // RFC 9457 code field (direct)
  if (err.code && typeof err.code === 'string') {
    return err.code
  }

  // openapi-fetch wrapper (cause.code)
  if (err.cause && typeof err.cause === 'object') {
    const cause = err.cause as { code?: unknown }
    if (typeof cause.code === 'string') {
      return cause.code
    }
  }

  // Data wrapper (WS errors, etc.)
  if (err.data && typeof err.data === 'object') {
    const data = err.data as { code?: unknown }
    if (typeof data.code === 'string') {
      return data.code
    }
  }

  return undefined
}

/** Human-readable titles for RFC 9457 error codes */
const ERROR_TITLES: Record<string, string> = {
  // Workflow errors
  WORKFLOW_NAME_CONFLICT: 'Workflow Name Conflict',
  WORKFLOW_DISABLED: 'Workflow Disabled',
  WORKFLOW_NOT_FOUND: 'Workflow Not Found',
  WORKFLOW_VERSION_NOT_FOUND: 'Workflow Version Not Found',
  WORKFLOW_DEFINITION_INVALID: 'Workflow Definition Invalid',
  // Provider/Tool errors
  PROVIDER_NAME_CONFLICT: 'Provider Name Conflict',
  PROVIDER_NOT_FOUND: 'Provider Not Found',
  TOOL_NOT_FOUND: 'Tool Not Found',
  TOOL_VALIDATION_ERROR: 'Tool Validation Error',
  // Validation errors
  VALIDATION_ERROR: 'Validation Error',
  FILE_VALIDATION_ERROR: 'File Validation Error',
  FILE_TOO_LARGE: 'File Too Large',
  UNSUPPORTED_FILE_FORMAT: 'Unsupported File Format',
  TOO_MANY_FILES: 'Too Many Files',
  // Settings errors
  VERSION_CONFLICT: 'Version Conflict',
  SETTING_NOT_FOUND: 'Setting Not Found',
  SETTING_VERSION_CONFLICT: 'Version Conflict',
  SETTING_VALIDATION_ERROR: 'Setting Validation Error',
  // Auth errors
  AUTHENTICATION_REQUIRED: 'Authentication Required',
  REQUEST_VALIDATION_ERROR: 'Request Validation Error',
  // AAP setup errors
  AAP_CONNECTION_ERROR: 'AAP Connection Error',
  AAP_AUTHENTICATION_ERROR: 'AAP Authentication Failed',
  AAP_SETUP_ERROR: 'AAP Setup Error',
  // System errors
  LLM_CONFIGURATION_ERROR: 'Configuration Error',
  TEMPORAL_UNAVAILABLE: 'Workflow Engine Unavailable',
  EXECUTION_NOT_FOUND: 'Execution Not Found',
  INTERNAL_ERROR: 'Internal Error',
}

/**
 * Returns a human-readable title for an RFC 9457 error.
 *
 * @param error - The error object
 * @returns Human-readable title or "Error" as fallback
 *
 * @example
 * const title = getErrorTitle(error)
 * showAlert({ title, message: getErrorMessage(error) })
 */
function extractEmbeddedErrorTitle(err: ApiError): string | undefined {
  if (err.title && typeof err.title === 'string') {
    return finalizeUserFacingMessage(err.title)
  }

  if (err.data && typeof err.data === 'object') {
    const data = err.data as { title?: unknown }
    if (typeof data.title === 'string') {
      return finalizeUserFacingMessage(data.title)
    }
  }

  if (err.cause && typeof err.cause === 'object') {
    const cause = err.cause as { title?: unknown }
    if (typeof cause.title === 'string') {
      return finalizeUserFacingMessage(cause.title)
    }
  }

  return undefined
}

export function getErrorTitle(error: unknown): string {
  if (error && typeof error === 'object') {
    const embedded = extractEmbeddedErrorTitle(error as ApiError)
    if (embedded) {
      return embedded
    }
  }

  const code = getErrorCode(error)
  if (code && ERROR_TITLES[code]) {
    return ERROR_TITLES[code]
  }

  return 'Error'
}

/**
 * Detects if an error is related to admin/system configuration.
 *
 * These errors typically require administrator intervention and include:
 * - Missing API keys (OPENROUTER_API_KEY, etc.)
 * - Service configuration issues
 * - 503 Service Unavailable errors
 *
 * @param error - The error object to check
 * @returns true if the error is a configuration-related error
 *
 * @example
 * if (isAdminConfigurationError(error)) {
 *   return <EmptyStateServiceUnavailable showAdminHint={true} />
 * }
 */
export function isAdminConfigurationError(error: unknown): boolean {
  // 503 errors are typically configuration issues
  if (isServiceUnavailableError(error)) {
    return true
  }

  // Check message for common configuration keywords
  const message = getErrorMessage(error).toLowerCase()
  const configKeywords = ['api_key', 'api key', 'not configured', 'configuration', 'environment variable']

  return configKeywords.some((keyword) => message.includes(keyword))
}

/**
 * Detects if an error is retryable based on RFC 9457 'retryable' flag.
 *
 * @param error - The error object to check
 * @returns true if the error has retryable=true or is a 5xx error
 *
 * @example
 * if (isRetryableError(error)) {
 *   return <Button onClick={retry}>Retry</Button>
 * }
 */
export function isRetryableError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false
  }

  const err = error as ApiError

  // Check retryable flag directly (RFC 9457)
  if (typeof err.retryable === 'boolean') {
    return err.retryable
  }

  // Check in nested locations (data wrapper, cause wrapper)
  if (err.data && typeof err.data === 'object') {
    const data = err.data as { retryable?: unknown }
    if (typeof data.retryable === 'boolean') {
      return data.retryable
    }
  }

  if (err.cause && typeof err.cause === 'object') {
    const cause = err.cause as { retryable?: unknown }
    if (typeof cause.retryable === 'boolean') {
      return cause.retryable
    }
  }

  // Default: treat 5xx errors as retryable (conservative fallback)
  const status = getErrorStatus(error)
  if (status && status >= 500 && status < 600) {
    return true
  }

  return false
}

/**
 * Detects if an error is a 409 Conflict error (name conflicts).
 *
 * @param error - The error object to check
 * @returns true if the error is a 409 Conflict error
 *
 * @example
 * if (isConflictError(error)) {
 *   showAlert({ title: 'Name already exists', variant: 'warning' })
 * }
 */
export function isConflictError(error: unknown): boolean {
  // Check RFC 9457 conflict error codes first (more specific)
  const code = getErrorCode(error)
  if (code === 'WORKFLOW_NAME_CONFLICT' || code === 'PROVIDER_NAME_CONFLICT') {
    return true
  }

  if (getErrorStatus(error) === 409) {
    return true
  }

  return false
}

/**
 * Detects if an error is a workflow version conflict (HTTP 409 with WORKFLOW_VERSION_CONFLICT code).
 *
 * Used by save and publish flows to detect when another user has saved a newer version
 * of the workflow while the current user was editing.
 *
 * @param error - The error object to check
 * @returns true if the error represents a workflow version conflict
 */
export function isWorkflowVersionConflictError(error: unknown): error is Record<string, unknown> {
  return getErrorCode(error) === 'WORKFLOW_VERSION_CONFLICT'
}

function getErrorBody(error: Record<string, unknown>): Record<string, unknown> {
  if (error.cause && typeof error.cause === 'object') return error.cause as Record<string, unknown>
  return error
}

export function extractVersionConflictInfo(error: Record<string, unknown>) {
  const body = getErrorBody(error)
  const createdAt = (body.created_at as string) ?? ''
  return {
    currentVersion: (body.current_version as number) ?? 0,
    currentVersionName: (body.current_version_name as string | null) ?? null,
    expectedVersion: (body.expected_version as number) ?? 0,
    expectedVersionName: (body.expected_version_name as string | null) ?? null,
    expectedVersionCreatedAt: (body.expected_created_at as string | null) ?? null,
    createdByUsername: (body.created_by_username as string) ?? 'another user',
    createdAt,
  }
}
