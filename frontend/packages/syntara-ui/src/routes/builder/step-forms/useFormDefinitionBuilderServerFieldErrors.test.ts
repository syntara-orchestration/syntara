import type { FormDefinition } from '@syntara/contracts'
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE, FormFieldTypeEnum } from '../../../forms'

import { useFormDefinitionFieldServerErrors } from './useFormDefinitionBuilderServerFieldErrors'

const invalidDateDefinition: FormDefinition = {
  fields: [
    {
      type: FormFieldTypeEnum.DATE,
      value_name: 'due',
      label: 'Due',
      include_date: true,
      include_time: false,
      include_timezone: true,
    },
  ],
}

describe('useFormDefinitionFieldServerErrors', () => {
  it('supplements banner-only verify errors with local include_time finding', () => {
    const effectiveServerValidationErrors = [
      {
        message: 'Form "Survey": Field 1 — Select a time when both date and timezone are selected.',
        fieldPath: null,
      },
    ]

    const { result } = renderHook(() =>
      useFormDefinitionFieldServerErrors(invalidDateDefinition, effectiveServerValidationErrors)
    )

    expect(result.current).toEqual([
      {
        fieldIndex: 0,
        subPath: 'include_time',
        message: DATE_FIELD_DATE_AND_TIMEZONE_REQUIRES_TIME_MESSAGE,
      },
    ])
  })

  it('returns no field errors while server validation is inactive', () => {
    const { result } = renderHook(() => useFormDefinitionFieldServerErrors(invalidDateDefinition, undefined))

    expect(result.current).toEqual([])
  })
})
