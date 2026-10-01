import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

import type { FormPromptFormData } from './formPromptNodeFormSchema'
import { mapFormPromptFormDataToSubmit } from './formPromptNodeFormSubmit'

function baseFormData(overrides: Partial<FormPromptFormData> = {}): FormPromptFormData {
  return {
    name: '  Survey  ',
    message: '  Hello  ',
    form_definition: createEmptyFormDefinition(),
    responder_users: [],
    responder_groups: [],
    submit_label: '  Send  ',
    success_message: '  Done  ',
    timezone: ' America/New_York ',
    css_override: ' .x { color: red; } ',
    settings: {},
    ...overrides,
  }
}

describe('mapFormPromptFormDataToSubmit', () => {
  it('trims strings and omits empty optional fields', () => {
    const result = mapFormPromptFormDataToSubmit(baseFormData(), false)
    expect(result.name).toBe('Survey')
    expect(result.message).toBe('Hello')
    expect(result.submit_label).toBe('Send')
    expect(result.success_message).toBe('Done')
    expect(result.timezone).toBe('America/New_York')
    expect(result.css_override).toBe('.x { color: red; }')
    expect(result.responder_users).toBeUndefined()
    expect(result.fallback_decision).toBe('submit')
  })

  it('forces submit fallback_decision when continue-on-failure is not effectively enabled', () => {
    const result = mapFormPromptFormDataToSubmit(
      baseFormData({ fallback_decision: 'fallback', settings: { continue_on_failure: false } }),
      false
    )
    expect(result.fallback_decision).toBe('submit')
  })

  it('keeps fallback_decision when continue-on-failure is effectively enabled', () => {
    const result = mapFormPromptFormDataToSubmit(
      baseFormData({ fallback_decision: 'fallback', settings: { continue_on_failure: true } }),
      false
    )
    expect(result.fallback_decision).toBe('fallback')
  })
})
