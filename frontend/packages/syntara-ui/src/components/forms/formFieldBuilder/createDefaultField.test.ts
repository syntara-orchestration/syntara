import type { FormField } from '@syntara/contracts'
import { FormFieldDisplayEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { FormFieldTypeEnum } from '../../../forms'
import { FORM_FIELD_UI_KIND_VALUES, FormFieldUiKindEnum, uiKindForField } from '../../../forms/formFieldUiKind'

import {
  createDefaultField,
  defaultDynamicOptionsSource,
  fieldTypeLabel,
  FORM_FIELD_TYPE_SELECT_OPTIONS,
  replaceFieldType,
} from './createDefaultField'

describe('createDefaultField', () => {
  it('creates dropdown fields with static options', () => {
    const field = createDefaultField(FormFieldTypeEnum.DROPDOWN, [])
    expect(field.type).toBe(FormFieldTypeEnum.DROPDOWN)
    if (field.type === FormFieldTypeEnum.DROPDOWN && field.options.source === 'static') {
      expect(field.options.values).toHaveLength(1)
    }
  })

  it('creates defaults for every supported field type', () => {
    for (const type of FORM_FIELD_UI_KIND_VALUES) {
      const field = createDefaultField(type, [])
      expect(uiKindForField(field)).toBe(type)
    }
  })

  it('keeps all nine field choices in the builder menu', () => {
    expect(FORM_FIELD_UI_KIND_VALUES).toHaveLength(9)
    expect(FORM_FIELD_TYPE_SELECT_OPTIONS.map(({ label }) => label)).toEqual([
      'Text',
      'Text area',
      'Masked text',
      'Email',
      'Number',
      'Checkbox',
      'Date',
      'Dropdown',
      'Multi-select',
    ])
  })

  it('leaves required dynamic option keys empty until the author sets them', () => {
    expect(defaultDynamicOptionsSource()).toEqual({
      source: 'dynamic',
      expression: '',
      label_key: '',
      value_key: '',
    })
  })

  it('fieldTypeLabel returns a human label for each type', () => {
    for (const type of FORM_FIELD_UI_KIND_VALUES) {
      expect(fieldTypeLabel(type)).not.toBe('')
    }
  })

  it('replaceFieldType returns the same field when type is unchanged', () => {
    const textField: FormField = {
      type: FormFieldTypeEnum.TEXT,
      value_name: 'x',
      label: 'X',
    }
    expect(replaceFieldType(textField, FormFieldUiKindEnum.TEXT, [])).toBe(textField)
  })

  it('switches between text display kinds even though the API type stays text', () => {
    const textField = createDefaultField(FormFieldUiKindEnum.TEXT)
    const textAreaField = replaceFieldType(textField, FormFieldUiKindEnum.TEXTAREA, [])

    expect(textAreaField).toMatchObject({ type: FormFieldTypeEnum.TEXT, display: FormFieldDisplayEnum.MULTI_LINE })
    expect(uiKindForField(textAreaField)).toBe(FormFieldUiKindEnum.TEXTAREA)
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
