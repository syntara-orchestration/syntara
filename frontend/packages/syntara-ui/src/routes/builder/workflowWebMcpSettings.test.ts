import { describe, expect, it } from 'vitest'

import { parseNodeSettings } from './workflowWebMcpSettings'

describe('parseNodeSettings', () => {
  it('accepts supported flags, timeout, and retry policy values', () => {
    expect(
      parseNodeSettings(
        {
          disabled: false,
          continue_on_failure: true,
          timeout: 30,
          retry_policy: {
            max_retries: 2,
            backoff: 'exponential',
            initial_interval: 1,
            max_interval: 10,
            backoff_coefficient: 2,
          },
        },
        'settings'
      )
    ).toEqual({
      disabled: false,
      continue_on_failure: true,
      timeout: 30,
      retry_policy: {
        max_retries: 2,
        backoff: 'exponential',
        initial_interval: 1,
        max_interval: 10,
        backoff_coefficient: 2,
      },
    })
  })

  it('returns undefined when settings are omitted', () => {
    expect(parseNodeSettings(undefined, 'settings')).toBeUndefined()
  })

  it.each([null, [], 'settings'])('rejects non-object settings: %s', (value) => {
    expect(() => parseNodeSettings(value, 'settings')).toThrow('settings must be an object.')
  })

  it('rejects unsupported setting keys and invalid flags', () => {
    expect(() => parseNodeSettings({ retries: 2 }, 'settings')).toThrow('settings.retries is not a supported setting.')
    expect(() => parseNodeSettings({ disabled: 'no' }, 'settings')).toThrow('settings.disabled must be true or false.')
  })

  it('rejects negative or invalid timeout and retry values', () => {
    expect(() => parseNodeSettings({ timeout: -1 }, 'settings')).toThrow(
      'settings.timeout must be a non-negative number.'
    )
    expect(() => parseNodeSettings({ timeout: Number.POSITIVE_INFINITY }, 'settings')).toThrow(
      'settings.timeout must be a non-negative number.'
    )
    expect(() => parseNodeSettings({ retry_policy: null }, 'settings')).toThrow(
      'settings.retry_policy must be an object.'
    )
    expect(() => parseNodeSettings({ retry_policy: { max_retries: 1.5 } }, 'settings')).toThrow(
      'settings.retry_policy.max_retries must be a non-negative integer.'
    )
    expect(() => parseNodeSettings({ retry_policy: { backoff: 'linear' } }, 'settings')).toThrow(
      'settings.retry_policy.backoff must be exponential or fixed.'
    )
  })
})
