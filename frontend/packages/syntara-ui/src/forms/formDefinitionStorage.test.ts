import type { FormDefinition } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../components/forms/formFieldBuilder/createDefaultField'

import { FormFieldTypeEnum, serializeFormDefinitionForStorage } from './index'

describe('serializeFormDefinitionForStorage', () => {
  it('returns strict parsed data when the definition is valid', () => {
    const input = createEmptyFormDefinition()
    const result = serializeFormDefinitionForStorage(input)
    expect(result.fields).toHaveLength(1)
    expect(result.fields[0]?.type).toBe(FormFieldTypeEnum.TEXT)
  })

  it('preserves draft definitions that fail strict validation', () => {
    const draft: FormDefinition = { fields: [] }
    expect(serializeFormDefinitionForStorage(draft)).toEqual({ fields: [] })
  })
})
