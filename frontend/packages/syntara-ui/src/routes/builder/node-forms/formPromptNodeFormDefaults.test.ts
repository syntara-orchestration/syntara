import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

import { getFormPromptNodeFormDefaultValues } from './formPromptNodeFormDefaults'

describe('getFormPromptNodeFormDefaultValues', () => {
  it('fills defaults when initial data is omitted', () => {
    const values = getFormPromptNodeFormDefaultValues()
    expect(values.name).toBe('')
    expect(values.submit_label).toBe('Submit')
    expect(values.success_message).toBe('Response submitted successfully.')
    expect(values.form_definition).toEqual(createEmptyFormDefinition())
    expect(values.fallback_decision).toBe('submit')
  })

  it('maps fallback_behavior to fallback_decision when decision is missing', () => {
    const values = getFormPromptNodeFormDefaultValues({
      name: 'Form',
      form_definition: createEmptyFormDefinition(),
      fallback_behavior: 'fallback',
    })
    expect(values.fallback_decision).toBe('fallback')
  })
})
