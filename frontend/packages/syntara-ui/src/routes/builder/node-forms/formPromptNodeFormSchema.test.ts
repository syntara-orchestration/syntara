import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

import { formPromptFormSchema, formPromptStoredParametersSchema } from './formPromptNodeFormSchema'

describe('formPromptFormSchema', () => {
  it('accepts a minimal valid form prompt payload', () => {
    const result = formPromptFormSchema.safeParse({
      name: 'Survey',
      form_definition: createEmptyFormDefinition(),
    })
    expect(result.success).toBe(true)
  })

  it('rejects too many responder groups', () => {
    const groups = Array.from({ length: 51 }, (_, i) => `group-${i}`)
    const result = formPromptFormSchema.safeParse({
      name: 'Survey',
      form_definition: createEmptyFormDefinition(),
      responder_groups: groups,
    })
    expect(result.success).toBe(false)
  })

  it('rejects too many responder users', () => {
    const users = Array.from({ length: 101 }, (_, i) => `user-${i}`)
    const result = formPromptFormSchema.safeParse({
      name: 'Survey',
      form_definition: createEmptyFormDefinition(),
      responder_users: users,
    })
    expect(result.success).toBe(false)
  })

  it('parses stored parameters with fallback_behavior', () => {
    const result = formPromptStoredParametersSchema.safeParse({
      fallback_behavior: 'fail',
      fallback_decision: 'submit',
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.fallback_behavior).toBe('fail')
    }
  })
})
