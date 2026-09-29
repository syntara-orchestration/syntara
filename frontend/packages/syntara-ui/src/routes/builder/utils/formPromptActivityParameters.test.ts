import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

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
})
