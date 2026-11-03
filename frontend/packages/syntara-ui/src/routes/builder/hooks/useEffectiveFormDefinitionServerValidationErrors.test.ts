import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FormFieldTypeEnum } from '../../../forms'

import { useEffectiveFormDefinitionServerValidationErrors } from './useEffectiveFormDefinitionServerValidationErrors'

const serverErrors = [{ message: 'Label is required', fieldPath: 'parameters.form_definition.fields.0.label' }]

const validDefinition = {
  fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' }],
}

const invalidDefinition = {
  fields: [{ type: FormFieldTypeEnum.TEXT, value_name: '', label: '' }],
}

describe('useEffectiveFormDefinitionServerValidationErrors', () => {
  it('returns undefined when there are no server errors', () => {
    const { result } = renderHook(() => useEffectiveFormDefinitionServerValidationErrors(invalidDefinition, undefined))

    expect(result.current).toBeUndefined()
  })

  it('returns server errors while the watched definition is invalid', () => {
    const { result } = renderHook(() =>
      useEffectiveFormDefinitionServerValidationErrors(invalidDefinition, serverErrors)
    )

    expect(result.current).toEqual(serverErrors)
  })

  it('returns undefined once the watched definition becomes valid', () => {
    const { result, rerender } = renderHook(
      ({ definition }) => useEffectiveFormDefinitionServerValidationErrors(definition, serverErrors),
      { initialProps: { definition: invalidDefinition } }
    )

    expect(result.current).toEqual(serverErrors)

    rerender({ definition: validDefinition })

    expect(result.current).toBeUndefined()
  })

  it('uses readPreparedDefinition when the outer watch is still stale', () => {
    const { result } = renderHook(() =>
      useEffectiveFormDefinitionServerValidationErrors(invalidDefinition, serverErrors, {
        readPreparedDefinition: () => validDefinition,
      })
    )

    expect(result.current).toBeUndefined()
  })

  it('passes server errors through when applyFormDefinitionValidityCheck is false', () => {
    const { result } = renderHook(() =>
      useEffectiveFormDefinitionServerValidationErrors(validDefinition, serverErrors, {
        applyFormDefinitionValidityCheck: false,
      })
    )

    expect(result.current).toEqual(serverErrors)
  })
})
