import { describe, expect, it } from 'vitest'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'

import { readStoredFormDefinition } from './readStoredFormDefinition'

describe('readStoredFormDefinition', () => {
  it('returns parsed form definition from parameters', () => {
    const definition = createEmptyFormDefinition()
    expect(readStoredFormDefinition({ form_definition: definition })).toEqual(definition)
  })

  it('returns undefined for missing or invalid parameters', () => {
    expect(readStoredFormDefinition(null)).toBeUndefined()
    expect(readStoredFormDefinition({ form_definition: 'invalid' })).toBeUndefined()
    expect(readStoredFormDefinition({})).toBeUndefined()
  })
})
