import type { FormDefinition } from '@syntara/contracts'
import type { FieldError, FieldErrors } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import {
  type DateIncludeTimeFieldErrors,
  dateFieldIncludeTimeErrorMessage,
} from './formFieldBuilderDateIncludeTimeError'

function rhfErrorsWithIncludeTimeMessage(message: string): FieldErrors<FormDefinition> {
  const includeTimeError: FieldError = { type: 'manual', message }
  const fieldErrors: DateIncludeTimeFieldErrors = { include_time: includeTimeError }
  return { fields: [fieldErrors] } as FieldErrors<FormDefinition>
}

describe('dateFieldIncludeTimeErrorMessage', () => {
  it('reads include_time message from nested field errors', () => {
    expect(dateFieldIncludeTimeErrorMessage(rhfErrorsWithIncludeTimeMessage('Select a time'), 0)).toBe('Select a time')
  })

  it('returns undefined when include_time has no message', () => {
    const errors: FieldErrors<FormDefinition> = { fields: [] }
    expect(dateFieldIncludeTimeErrorMessage(errors, 0)).toBeUndefined()
  })
})
