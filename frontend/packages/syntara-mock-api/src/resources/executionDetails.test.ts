import { describe, expect, it } from 'vitest'

import { getExecutionDetail } from './executionDetails'

describe('getExecutionDetail', () => {
  it('propagates stall_alert_at from ActivityExecution to ActivityData', () => {
    const detail = getExecutionDetail('exec-stalled')

    expect(detail).toBeDefined()
    expect(detail?.activities).toHaveLength(1)
    expect(detail?.activities?.[0]).toMatchObject({
      activity_id: 'check_temperature',
      status: 'running',
      stall_alert_at: expect.any(String),
    })
  })

  it('includes first_stall_detected_at on execution', () => {
    const detail = getExecutionDetail('exec-stalled')

    expect(detail).toBeDefined()
    expect(detail?.first_stall_detected_at).toBeDefined()
    expect(detail?.first_stall_detected_at).toBe('2026-06-15T09:30:00.000Z') // minutesAgo30
  })

  it('returns undefined stall_alert_at for non-stalled activities', () => {
    const detail = getExecutionDetail('exec-1')

    expect(detail).toBeDefined()
    expect(detail?.activities).toBeDefined()
    expect(detail?.activities?.[0]?.stall_alert_at).toBeUndefined()
  })

  it('exec-stalled uses deterministic timestamps for stable visual regression', () => {
    const detail = getExecutionDetail('exec-stalled')

    expect(detail).toBeDefined()
    expect(detail?.started_at).toBe('2026-06-15T09:15:00.000Z') // minutesAgo45
  })
})
