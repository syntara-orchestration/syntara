import type { FormField } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { FORM_FIELD_TYPE_VALUES, FormFieldTypeEnum } from '../../../forms'

import { createDefaultField, fieldTypeLabel, replaceFieldType } from './createDefaultField'

describe('createDefaultField', () => {
  it('creates dropdown fields with static options', () => {
    const field = createDefaultField(FormFieldTypeEnum.DROPDOWN, [])
    expect(field.type).toBe(FormFieldTypeEnum.DROPDOWN)
    if (field.type === FormFieldTypeEnum.DROPDOWN && field.options.source === 'static') {
      expect(field.options.values).toHaveLength(1)
    }
  })

  it('creates defaults for every supported field type', () => {
    for (const type of FORM_FIELD_TYPE_VALUES) {
      const field = createDefaultField(type, [])
      expect(field.type).toBe(type)
    }
  })

  it('fieldTypeLabel returns a human label for each type', () => {
    for (const type of FORM_FIELD_TYPE_VALUES) {
      expect(fieldTypeLabel(type)).not.toBe('')
    }
  })

  it('replaceFieldType returns the same field when type is unchanged', () => {
    const textField: FormField = {
      type: FormFieldTypeEnum.TEXT,
      value_name: 'x',
      label: 'X',
    }
    expect(replaceFieldType(textField, FormFieldTypeEnum.TEXT, [])).toBe(textField)
  })

  it('replaceFieldType preserves label and value_name', () => {
    const textField: FormField = {
      type: FormFieldTypeEnum.TEXT,
      value_name: 'reason',
      label: 'Reason',
    }
    const numberField = replaceFieldType(textField, FormFieldTypeEnum.NUMBER, ['reason'])
    expect(numberField.type).toBe(FormFieldTypeEnum.NUMBER)
    expect(numberField.value_name).toBe('reason')
    expect(numberField.label).toBe('Reason')
  })
})
