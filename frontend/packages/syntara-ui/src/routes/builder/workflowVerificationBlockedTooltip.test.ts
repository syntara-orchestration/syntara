import { describe, expect, it } from 'vitest'

import { workflowVerificationBlockedTooltip } from './workflowVerificationBlockedTooltip'

describe('workflowVerificationBlockedTooltip', () => {
  it('uses singular error for count of 1', () => {
    expect(workflowVerificationBlockedTooltip('publishing', 1)).toBe(
      'Verify your workflow before publishing — 1 error found'
    )
    expect(workflowVerificationBlockedTooltip('running', 1)).toBe('Verify your workflow before running — 1 error found')
  })

  it('uses plural errors for count greater than 1', () => {
    expect(workflowVerificationBlockedTooltip('publishing', 3)).toBe(
      'Verify your workflow before publishing — 3 errors found'
    )
    expect(workflowVerificationBlockedTooltip('running', 2)).toBe(
      'Verify your workflow before running — 2 errors found'
    )
  })
})
