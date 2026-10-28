import { TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { validateFormTriggerFormDefinition } from './validateFormTriggerFormDefinition'

describe('validateFormTriggerFormDefinition', () => {
  it('returns no errors when context is undefined and graph is empty', () => {
    expect(validateFormTriggerFormDefinition([], [], undefined)).toEqual([])
  })

  it('returns an error when form trigger has no fields', () => {
    const errors = validateFormTriggerFormDefinition([], [], {
      triggers: [
        {
          id: 'form',
          type: TriggerTypeEnum.FORM_TRIGGER,
          name: 'Intake',
          parameters: { form_definition: { fields: [] } },
        },
      ],
    })
    expect(errors).toHaveLength(1)
    expect(errors[0].rule).toBe('form-trigger-form-definition')
    expect(errors[0].nodeId).toBe('form')
    expect(errors[0].message).toContain('Intake')
  })

  it('ignores non form triggers', () => {
    const errors = validateFormTriggerFormDefinition([], [], {
      triggers: [
        {
          id: 'manual',
          type: TriggerTypeEnum.MANUAL_TRIGGER,
          parameters: {},
        },
      ],
    })
    expect(errors).toEqual([])
  })

  it('flags manual trigger that carries form trigger parameters', () => {
    const errors = validateFormTriggerFormDefinition([], [], {
      triggers: [
        {
          id: 'form',
          type: TriggerTypeEnum.MANUAL_TRIGGER,
          name: 'Intake',
          parameters: {
            message: 'Enter details',
            form_definition: { fields: [{ type: 'text', value_name: 'x', label: 'X' }] },
            submit_label: 'Submit',
            success_message: 'Done',
          },
        },
      ],
    })
    expect(errors).toHaveLength(1)
    expect(errors[0].rule).toBe('form-trigger-type-mismatch')
    expect(errors[0].message).toContain('manual_trigger')
  })
})
