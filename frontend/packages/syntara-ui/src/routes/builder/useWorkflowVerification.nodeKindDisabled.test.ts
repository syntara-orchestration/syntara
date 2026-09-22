import { describe, expect, it } from 'vitest'

import { extractValidationErrors, extractValidationErrorsFromUnknown } from './useWorkflowVerification'

/**
 * A node whose kind was switched off platform-wide produces an ERROR finding
 * carrying the offending `node_id`. The builder's existing findings pipeline
 * turns that node id into the per-node warning badge on the canvas, so the kill
 * switch needs no separate canvas plumbing (F-13/F-17).
 */
const disabledFinding = {
  message: "Node kind 'agentic' is disabled",
  node_id: 'activity-1',
  severity: 'error',
  category: 'node_kind_disabled',
  field_path: null,
}

describe('node_kind_disabled findings', () => {
  it('keeps the node id so the canvas can badge the node', () => {
    const errors = extractValidationErrors({ validation_result: { findings: [disabledFinding] } })

    expect(errors).toHaveLength(1)
    expect(errors?.[0].nodeId).toBe('activity-1')
    expect(errors?.[0].severity).toBe('error')
  })

  it('surfaces the backend message to the user', () => {
    const errors = extractValidationErrors({ validation_result: { findings: [disabledFinding] } })

    expect(errors?.[0].message).toContain("Node kind 'agentic' is disabled")
  })

  it('reads the finding out of a rejected save body', () => {
    const errors = extractValidationErrorsFromUnknown({
      cause: { validation_result: { findings: [disabledFinding] } },
    })

    expect(errors?.[0].nodeId).toBe('activity-1')
  })

  it('keeps a removal warning as a warning', () => {
    const errors = extractValidationErrors({
      validation_result: {
        findings: [{ ...disabledFinding, severity: 'warning', message: 'Disabled nodes were removed' }],
      },
    })

    expect(errors?.[0].severity).toBe('warning')
  })
})
