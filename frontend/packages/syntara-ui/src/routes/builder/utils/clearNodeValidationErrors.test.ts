import { describe, expect, it, vi } from 'vitest'

import { FormFieldTypeEnum } from '../../../forms'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { ValidationError } from '../builderReducer'

import {
  clearNodeValidationErrorsIfFormDefinitionValid,
  isStoredFormDefinitionValid,
} from './clearNodeValidationErrors'

describe('isStoredFormDefinitionValid', () => {
  it('returns false when required field details are missing', () => {
    expect(
      isStoredFormDefinitionValid({
        fields: [{ type: FormFieldTypeEnum.TEXT, value_name: '', label: '' }],
      })
    ).toBe(false)
  })

  it('returns true when the definition passes strict validation', () => {
    expect(
      isStoredFormDefinitionValid({
        fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' }],
      })
    ).toBe(true)
  })
})

describe('clearNodeValidationErrorsIfFormDefinitionValid', () => {
  const validDefinition = {
    fields: [{ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' }],
  }

  it('does nothing when the form definition is still invalid', () => {
    const dispatch = vi.fn()
    const setValidationErrorCount = vi.fn()
    vi.spyOn(useWorkflowStore, 'getState').mockReturnValue({
      setValidationErrorCount,
    } as unknown as ReturnType<typeof useWorkflowStore.getState>)

    clearNodeValidationErrorsIfFormDefinitionValid({
      dispatch,
      getValidationErrors: () => [{ message: 'Bad field', nodeId: 'node-1' }],
      nodeId: 'node-1',
      formDefinition: { fields: [{ type: FormFieldTypeEnum.TEXT, value_name: '', label: '' }] },
    })

    expect(dispatch).not.toHaveBeenCalled()
    expect(setValidationErrorCount).not.toHaveBeenCalled()
  })

  it('dispatches CLEAR_NODE_VALIDATION_ERRORS and updates the error count when valid', () => {
    const dispatch = vi.fn()
    const setValidationErrorCount = vi.fn()
    vi.spyOn(useWorkflowStore, 'getState').mockReturnValue({
      setValidationErrorCount,
    } as unknown as ReturnType<typeof useWorkflowStore.getState>)

    const errors: ValidationError[] = [
      { message: 'Field label required', nodeId: 'node-1', fieldPath: 'parameters.form_definition.fields.0.label' },
      { message: 'Other step', nodeId: 'node-2' },
    ]

    clearNodeValidationErrorsIfFormDefinitionValid({
      dispatch,
      getValidationErrors: () => errors,
      nodeId: 'node-1',
      formDefinition: validDefinition,
    })

    expect(dispatch).toHaveBeenCalledWith({
      type: 'CLEAR_NODE_VALIDATION_ERRORS',
      payload: { nodeId: 'node-1' },
    })
    expect(setValidationErrorCount).toHaveBeenCalledWith(1)
  })

  it('skips dispatch when there are no form-definition findings for the node', () => {
    const dispatch = vi.fn()
    vi.spyOn(useWorkflowStore, 'getState').mockReturnValue({
      setValidationErrorCount: vi.fn(),
    } as unknown as ReturnType<typeof useWorkflowStore.getState>)

    clearNodeValidationErrorsIfFormDefinitionValid({
      dispatch,
      getValidationErrors: () => [
        { message: 'Missing connection', nodeId: 'node-1', rule: 'form-prompt-connections' },
        { message: 'Other step', nodeId: 'node-2' },
      ],
      nodeId: 'node-1',
      formDefinition: validDefinition,
    })

    expect(dispatch).not.toHaveBeenCalled()
  })

  it('updates blocking count without removing unrelated findings on the same node', () => {
    const dispatch = vi.fn()
    const setValidationErrorCount = vi.fn()
    vi.spyOn(useWorkflowStore, 'getState').mockReturnValue({
      setValidationErrorCount,
    } as unknown as ReturnType<typeof useWorkflowStore.getState>)

    const errors: ValidationError[] = [
      { message: 'Field label required', nodeId: 'node-1', fieldPath: 'parameters.form_definition.fields.0.label' },
      { message: 'Missing connection', nodeId: 'node-1', rule: 'form-prompt-connections' },
    ]

    clearNodeValidationErrorsIfFormDefinitionValid({
      dispatch,
      getValidationErrors: () => errors,
      nodeId: 'node-1',
      formDefinition: validDefinition,
    })

    expect(dispatch).toHaveBeenCalledWith({
      type: 'CLEAR_NODE_VALIDATION_ERRORS',
      payload: { nodeId: 'node-1' },
    })
    expect(setValidationErrorCount).toHaveBeenCalledWith(1)
  })
})
