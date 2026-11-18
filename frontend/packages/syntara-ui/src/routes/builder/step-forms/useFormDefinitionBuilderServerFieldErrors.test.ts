import type { FormDefinition } from '@syntara/contracts'
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DATE_FIELD_RFC3339_COMBINATION_MESSAGE, FormFieldTypeEnum } from '../../../forms'

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
  it('maps canvas banner copy with field_path to short inline messages', () => {
    const effectiveServerValidationErrors = [
      {
        message: `Form "Survey": Due — ${DATE_FIELD_RFC3339_COMBINATION_MESSAGE}`,
        fieldPath: 'parameters.form_definition.fields.0.include_date',
      },
    ]

    const { result } = renderHook(() =>
      useFormDefinitionFieldServerErrors(invalidDateDefinition, effectiveServerValidationErrors)
    )

    expect(result.current).toEqual([
      {
        fieldIndex: 0,
        subPath: 'include_date',
        message: DATE_FIELD_RFC3339_COMBINATION_MESSAGE,
      },
    ])
  })

  it('supplements banner-only verify errors with local include_date finding', () => {
    const effectiveServerValidationErrors = [
      {
        message: `Form "Survey": Due — ${DATE_FIELD_RFC3339_COMBINATION_MESSAGE}`,
        fieldPath: null,
      },
    ]

    const { result } = renderHook(() =>
      useFormDefinitionFieldServerErrors(invalidDateDefinition, effectiveServerValidationErrors)
    )

    expect(result.current).toEqual([
      {
        fieldIndex: 0,
        subPath: 'include_date',
        message: DATE_FIELD_RFC3339_COMBINATION_MESSAGE,
      },
    ])
  })

  it('returns no field errors while server validation is inactive', () => {
    const { result } = renderHook(() => useFormDefinitionFieldServerErrors(invalidDateDefinition, undefined))

    expect(result.current).toEqual([])
  })
})
