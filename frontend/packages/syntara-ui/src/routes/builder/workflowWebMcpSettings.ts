import type { NodeSettings, RetryPolicyConfig } from '@syntara/contracts'

function isRecord(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const prototype = Object.getPrototypeOf(value) as unknown
  return prototype === Object.prototype || prototype === null
}

function assertAllowedKeys(value: Record<string, unknown>, path: string, allowedKeys: string[]): void {
  const allowed = new Set(allowedKeys)
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`${path}.${key} is not a supported setting.`)
  }
}

function parseNonNegativeNumber(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new Error(`${path} must be a non-negative number.`)
  }
  return value
}

function parseNonNegativeInteger(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    throw new Error(`${path} must be a non-negative integer.`)
  }
  return value
}

function parseRetryPolicy(value: unknown, path: string): RetryPolicyConfig {
  if (!isRecord(value)) throw new Error(`${path} must be an object.`)
  assertAllowedKeys(value, path, ['max_retries', 'backoff', 'initial_interval', 'max_interval', 'backoff_coefficient'])

  const policy: RetryPolicyConfig = {}
  if (value.max_retries !== undefined) {
    policy.max_retries = parseNonNegativeInteger(value.max_retries, `${path}.max_retries`)
  }
  if (value.backoff !== undefined) {
    if (value.backoff !== 'exponential' && value.backoff !== 'fixed') {
      throw new Error(`${path}.backoff must be exponential or fixed.`)
    }
    policy.backoff = value.backoff
  }
  for (const key of ['initial_interval', 'max_interval', 'backoff_coefficient'] as const) {
    if (value[key] !== undefined) policy[key] = parseNonNegativeNumber(value[key], `${path}.${key}`)
  }
  return policy
}

export function parseNodeSettings(value: unknown, path: string): NodeSettings | undefined {
  if (value === undefined) return undefined
  if (!isRecord(value)) throw new Error(`${path} must be an object.`)
  assertAllowedKeys(value, path, ['disabled', 'continue_on_failure', 'timeout', 'retry_policy'])

  const settings: NodeSettings = {}
  for (const key of ['disabled', 'continue_on_failure'] as const) {
    if (value[key] !== undefined) {
      if (typeof value[key] !== 'boolean') throw new Error(`${path}.${key} must be true or false.`)
      settings[key] = value[key]
    }
  }
  if (value.timeout !== undefined) settings.timeout = parseNonNegativeNumber(value.timeout, `${path}.timeout`)
  if (value.retry_policy !== undefined)
    settings.retry_policy = parseRetryPolicy(value.retry_policy, `${path}.retry_policy`)
  return settings
}
