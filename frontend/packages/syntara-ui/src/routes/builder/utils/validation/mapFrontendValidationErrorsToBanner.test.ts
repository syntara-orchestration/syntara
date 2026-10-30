import { describe, expect, it } from 'vitest'

import {
  countBlockingValidationErrors,
  mapUtilsValidationErrorsToBanner,
} from './mapFrontendValidationErrorsToBanner'
import type { ValidationError as UtilsValidationError } from './types'

describe('mapUtilsValidationErrorsToBanner', () => {
  it('maps utils validation errors to banner shape', () => {
    const errors: UtilsValidationError[] = [
      {
        id: 'e1',
        severity: 'error',
        rule: 'minimum-workflow-no-connection',
        message: 'Workflow must have at least one connection between trigger and steps',
      },
    ]

    expect(mapUtilsValidationErrorsToBanner(errors)).toEqual([
      {
        message: errors[0].message,
        nodeId: null,
        nodeName: undefined,
        severity: 'error',
      },
    ])
  })
})

describe('countBlockingValidationErrors', () => {
  it('counts only non-warning banner errors', () => {
    expect(
      countBlockingValidationErrors([
        { message: 'a', nodeId: null, severity: 'error' },
        { message: 'b', nodeId: null, severity: 'warning' },
      ])
    ).toBe(1)
  })
})
