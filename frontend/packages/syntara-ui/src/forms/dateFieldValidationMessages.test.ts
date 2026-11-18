import { describe, expect, it } from 'vitest'

import {
  DATE_FIELD_RFC3339_COMBINATION_MESSAGE,
  normalizeDateFieldCombinationMessage,
} from './dateFieldValidationMessages'

describe('normalizeDateFieldCombinationMessage', () => {
  it('returns the standard message for backend API copy', () => {
    expect(
      normalizeDateFieldCombinationMessage(
        "Field 'due': unsupported combination of date components. Choose a date; a time with a timezone; or a date, time, and timezone."
      )
    ).toBe(DATE_FIELD_RFC3339_COMBINATION_MESSAGE)
  })
})
