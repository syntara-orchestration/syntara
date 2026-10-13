import type { FormDefinition } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { FormFieldTypeEnum } from '../../../forms'

import { buildFormPromptActivityParameters } from './formPromptActivityParameters'

describe('buildFormPromptActivityParameters', () => {
  it('always includes form_definition and omits empty optional fields', () => {
    const form_definition = createEmptyFormDefinition()
    expect(
      buildFormPromptActivityParameters({
        form_definition,
        message: '',
        submit_label: null,
      })
    ).toEqual({ form_definition })
  })

  it('includes populated optional fields', () => {
    const form_definition = createEmptyFormDefinition()
    expect(
      buildFormPromptActivityParameters({
        form_definition,
        message: 'Hello',
        fallback_decision: 'submit',
        responder_users: ['alice'],
        response_window: 3600,
      })
    ).toMatchObject({
      form_definition,
      message: 'Hello',
      fallback_decision: 'submit',
      responder_users: ['alice'],
      response_window: 3600,
    })
  })

  it('throws when form definition fails validation', () => {
    const invalid: FormDefinition = {
      fields: [
        {
          type: FormFieldTypeEnum.TEXT,
          value_name: 'not-a-valid-name!',
          label: 'Bad',
        },
      ],
    }

    expect(() => buildFormPromptActivityParameters({ form_definition: invalid })).toThrow()
  })

  it('repairs date fields with time but no timezone before building parameters', () => {
    const form_definition: FormDefinition = {
      fields: [
        {
          type: FormFieldTypeEnum.DATE,
          value_name: 'due',
          label: 'Due',
          include_date: true,
          include_time: true,
          include_timezone: false,
        },
      ],
    }

    const params = buildFormPromptActivityParameters({ form_definition })
    const field = (params.form_definition as FormDefinition).fields[0]
    expect(field).toMatchObject({
      type: 'date',
      include_time: true,
      include_timezone: true,
    })
  })
})
