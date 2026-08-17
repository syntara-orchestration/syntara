import { MissedSchedulePolicyEnum, TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { isValidWebhookPath, normalizeWebhookPath, triggerFormSchema } from './triggerFormSchema'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseWebhook(webhookPath: string, inputSchema?: string) {
  return triggerFormSchema.safeParse({
    triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
    webhookPath,
    inputSchema,
  })
}

function parseEda(webhookPath: string, inputSchema?: string) {
  return triggerFormSchema.safeParse({
    triggerType: TriggerTypeEnum.EDA_TRIGGER,
    webhookPath,
    inputSchema,
  })
}

function parseManual(inputSchema?: string) {
  return triggerFormSchema.safeParse({
    triggerType: TriggerTypeEnum.MANUAL_TRIGGER,
    inputSchema,
  })
}

function parseScheduled(scheduleType: string, interval?: string, cron?: string) {
  return triggerFormSchema.safeParse({
    triggerType: TriggerTypeEnum.SCHEDULED,
    scheduleType,
    interval,
    cron,
  })
}

// ---------------------------------------------------------------------------
// normalizeWebhookPath
// ---------------------------------------------------------------------------

describe('normalizeWebhookPath', () => {
  it('strips leading slashes', () => {
    expect(normalizeWebhookPath('///path')).toBe('path')
  })

  it('lowercases mixed case', () => {
    expect(normalizeWebhookPath('Jira-Updates')).toBe('jira-updates')
  })

  it('preserves internal hyphens and underscores', () => {
    expect(normalizeWebhookPath('my_hook-1')).toBe('my_hook-1')
  })

  it('trims whitespace', () => {
    expect(normalizeWebhookPath('  path  ')).toBe('path')
  })

  it('handles empty string', () => {
    expect(normalizeWebhookPath('')).toBe('')
  })

  it('strips leading slashes and lowercases together', () => {
    expect(normalizeWebhookPath('//My-Path')).toBe('my-path')
  })
})

// ---------------------------------------------------------------------------
// isValidWebhookPath
// ---------------------------------------------------------------------------

describe('isValidWebhookPath', () => {
  it('returns true for a valid slug', () => {
    expect(isValidWebhookPath('jira-updates')).toBe(true)
  })

  it('returns true for a single character', () => {
    expect(isValidWebhookPath('a')).toBe(true)
  })

  it('returns false for path with slashes', () => {
    expect(isValidWebhookPath('api/v2/events')).toBe(false)
  })

  it('returns false for empty string', () => {
    expect(isValidWebhookPath('')).toBe(false)
  })

  it('returns false for path with dots', () => {
    expect(isValidWebhookPath('has.dots')).toBe(false)
  })

  it('returns false for path starting with hyphen', () => {
    expect(isValidWebhookPath('-leading')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Webhook path validation
// ---------------------------------------------------------------------------

describe('triggerFormSchema — webhook path validation', () => {
  describe('valid paths', () => {
    it('accepts a basic slug', () => {
      expect(parseWebhook('jira-updates').success).toBe(true)
    })

    it('accepts a single character', () => {
      expect(parseWebhook('a').success).toBe(true)
    })

    it('accepts mixed alphanumeric with hyphens', () => {
      expect(parseWebhook('my-webhook-123').success).toBe(true)
    })

    it('accepts underscores', () => {
      expect(parseWebhook('test_path').success).toBe(true)
    })

    it('accepts a leading slash (stripped by normalization)', () => {
      expect(parseWebhook('/jira-updates').success).toBe(true)
    })

    it('accepts mixed case (normalized to lowercase)', () => {
      expect(parseWebhook('Jira-Updates').success).toBe(true)
    })

    it('accepts multiple leading slashes (stripped by normalization)', () => {
      expect(parseWebhook('///my-path').success).toBe(true)
    })

    it('accepts path at exactly 128 characters', () => {
      expect(parseWebhook('a'.repeat(128)).success).toBe(true)
    })
  })

  describe('permissive paths (empty allowed, format still validated)', () => {
    it('accepts empty path', () => {
      expect(parseWebhook('').success).toBe(true)
    })

    it('accepts whitespace-only path', () => {
      expect(parseWebhook('   ').success).toBe(true)
    })

    it('rejects path exceeding 128 characters', () => {
      const result = parseWebhook('a'.repeat(129))
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.find((i) => i.path.includes('webhookPath'))?.message).toBe(
          'Webhook path must be 128 characters or fewer'
        )
      }
    })

    it('rejects path with path traversal sequences', () => {
      expect(parseWebhook('foo/../bar').success).toBe(false)
    })

    it('rejects paths with invalid format', () => {
      expect(parseWebhook('-starts-with-hyphen').success).toBe(false)
      expect(parseWebhook('has spaces').success).toBe(false)
      expect(parseWebhook('has.dots').success).toBe(false)
      expect(parseWebhook('has/slash').success).toBe(false)
      expect(parseWebhook('ends-with-hyphen-').success).toBe(false)
    })
  })
})

// ---------------------------------------------------------------------------
// Webhook trigger inputSchema validation
// ---------------------------------------------------------------------------

describe('triggerFormSchema — webhook trigger inputSchema (permissive)', () => {
  it('accepts a valid JSON object', () => {
    expect(parseWebhook('valid', '{"type": "object"}').success).toBe(true)
  })

  it('accepts empty inputSchema (optional field)', () => {
    expect(parseWebhook('valid', '').success).toBe(true)
  })

  it('accepts undefined inputSchema', () => {
    expect(parseWebhook('valid', undefined).success).toBe(true)
  })

  it('rejects invalid JSON inputSchema', () => {
    expect(parseWebhook('valid', '{bad}').success).toBe(false)
  })

  it('rejects non-object JSON inputSchema', () => {
    expect(parseWebhook('valid', '"hello"').success).toBe(false)
    expect(parseWebhook('valid', '42').success).toBe(false)
  })

  it('rejects array JSON inputSchema', () => {
    expect(parseWebhook('valid', '[]').success).toBe(false)
  })

  it('rejects boolean JSON inputSchema', () => {
    expect(parseWebhook('valid', 'true').success).toBe(false)
  })

  it('rejects null JSON inputSchema', () => {
    expect(parseWebhook('valid', 'null').success).toBe(false)
  })

  it('rejects inputSchema exceeding 100KB', () => {
    const largeSchema = `{"key": "${'x'.repeat(100_001)}"}`
    const result = parseWebhook('valid', largeSchema)
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.find((i) => i.path.includes('inputSchema'))?.message).toBe(
        'Input schema must be 100KB or less'
      )
    }
  })

  it('strips prototype pollution keys via safeJSONReviver', () => {
    const result = parseWebhook('valid', '{"__proto__": {"polluted": true}, "safe": 1}')
    expect(result.success).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Scheduled trigger validation
// ---------------------------------------------------------------------------

describe('triggerFormSchema — scheduled trigger', () => {
  it('rejects empty interval', () => {
    const result = parseScheduled('interval', '')
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.find((i) => i.path.includes('interval'))?.message).toBe('A schedule is required')
    }
  })

  it('accepts present interval', () => {
    expect(parseScheduled('interval', 'R/2024-01-01T00:00:00Z/P1D').success).toBe(true)
  })

  it('accepts valid 5-field cron expression', () => {
    expect(parseScheduled('cron', undefined, '0 9 * * *').success).toBe(true)
  })

  it('rejects empty cron', () => {
    const result = parseScheduled('cron', undefined, '')
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.find((i) => i.path.includes('cron'))?.message).toBe('Cron expression is required')
    }
  })

  it('rejects cron exceeding 256 characters (max length kept)', () => {
    const longCron = `${Array(150).fill('1').join(',')} * * * *`
    const result = parseScheduled('cron', undefined, longCron)
    expect(result.success).toBe(false)
  })

  it('rejects cron with wrong number of fields', () => {
    const result = parseScheduled('cron', undefined, '0 9 *')
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.find((i) => i.path.includes('cron'))?.message).toBe(
        'Cron expression must have exactly 5 fields: minute hour day-of-month month day-of-week'
      )
    }
  })

  it('rejects cron with invalid characters', () => {
    const result = parseScheduled('cron', undefined, '0 9 * * MON')
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.find((i) => i.path.includes('cron'))?.message).toBe(
        'Cron fields may only contain digits, *, /, -, and ,'
      )
    }
  })

  it('rejects non-cron text in cron field', () => {
    const result = parseScheduled('cron', undefined, 'hello world')
    expect(result.success).toBe(false)
  })

  it('rejects interval when end date is before start date', () => {
    const result = parseScheduled('interval', 'R/2024-06-15T10:00:00Z/P1D/2024-06-01T23:59:59Z')
    expect(result.success).toBe(false)
    if (!result.success) {
      const intervalError = result.error.issues.find((i) => i.path.includes('interval'))?.message
      expect(intervalError).toBe('End date must be on or after the start date')
    }
  })

  it('accepts interval when end date is after start date', () => {
    expect(parseScheduled('interval', 'R/2024-01-15T10:00:00Z/P1D/2024-12-31T23:59:59Z').success).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Manual trigger inputSchema validation
// ---------------------------------------------------------------------------

describe('triggerFormSchema — manual trigger inputSchema (permissive)', () => {
  it('accepts a valid JSON object', () => {
    expect(parseManual('{"type": "object"}').success).toBe(true)
  })

  it('accepts empty inputSchema (optional field)', () => {
    expect(parseManual('').success).toBe(true)
  })

  it('accepts undefined inputSchema', () => {
    expect(parseManual(undefined).success).toBe(true)
  })

  it('rejects invalid JSON inputSchema', () => {
    expect(parseManual('{bad}').success).toBe(false)
  })

  it('rejects non-object JSON inputSchema', () => {
    expect(parseManual('"hello"').success).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// EDA trigger validation (same rules as webhook)
// ---------------------------------------------------------------------------

describe('triggerFormSchema — EDA trigger (permissive)', () => {
  it('accepts valid EDA trigger with path', () => {
    expect(parseEda('eda-events').success).toBe(true)
  })

  it('accepts empty webhook path', () => {
    expect(parseEda('').success).toBe(true)
  })

  it('accepts valid inputSchema JSON', () => {
    expect(parseEda('eda-events', '{"type": "object"}').success).toBe(true)
  })

  it('rejects invalid inputSchema', () => {
    expect(parseEda('eda-events', 'not-json').success).toBe(false)
  })
})

describe('triggerFormSchema — missed schedule policy (overlap)', () => {
  function parseWithPolicy(policy: string) {
    return triggerFormSchema.safeParse({
      triggerType: TriggerTypeEnum.SCHEDULED,
      scheduleType: 'cron',
      cron: '0 9 * * *',
      missedSchedulePolicy: policy,
    })
  }

  it.each([
    MissedSchedulePolicyEnum.SKIP,
    MissedSchedulePolicyEnum.BUFFER_ONE,
    MissedSchedulePolicyEnum.BUFFER_ALL,
    MissedSchedulePolicyEnum.ALLOW_ALL,
    MissedSchedulePolicyEnum.CANCEL_OTHER,
  ])('accepts valid policy "%s"', (policy) => {
    expect(parseWithPolicy(policy).success).toBe(true)
  })

  it('rejects unknown policy value', () => {
    expect(parseWithPolicy('terminate_other').success).toBe(false)
  })

  it('rejects the old "run_once" policy value', () => {
    expect(parseWithPolicy('run_once').success).toBe(false)
  })

  it('rejects the old "run_all" policy value', () => {
    expect(parseWithPolicy('run_all').success).toBe(false)
  })

  it('accepts omitted policy (optional field)', () => {
    const result = triggerFormSchema.safeParse({
      triggerType: TriggerTypeEnum.SCHEDULED,
      scheduleType: 'cron',
      cron: '0 9 * * *',
    })
    expect(result.success).toBe(true)
  })
})
