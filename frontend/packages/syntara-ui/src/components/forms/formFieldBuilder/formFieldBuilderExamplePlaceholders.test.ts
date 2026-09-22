import { describe, expect, it } from 'vitest'

import { FormFieldTypeEnum } from '../../../forms'

import { getFormFieldBuilderExamplePlaceholders } from './formFieldBuilderExamplePlaceholders'

describe('getFormFieldBuilderExamplePlaceholders', () => {
  it('returns distinct examples per field type', () => {
    const text = getFormFieldBuilderExamplePlaceholders(FormFieldTypeEnum.TEXT)
    const email = getFormFieldBuilderExamplePlaceholders(FormFieldTypeEnum.EMAIL)
    expect(text.placeholder).not.toBe(email.placeholder)
    expect(email.placeholder).toContain('@')
  })

  it('covers every supported field type', () => {
    for (const type of Object.values(FormFieldTypeEnum)) {
      const examples = getFormFieldBuilderExamplePlaceholders(type)
      expect(examples.placeholder.length).toBeGreaterThan(0)
      expect(examples.helpText.length).toBeGreaterThan(0)
      expect(examples.defaultValue.length).toBeGreaterThan(0)
    }
  })
})
