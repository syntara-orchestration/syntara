import { FormFieldDisplayEnum, FormFieldTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { createDefaultField } from '../components/forms/formFieldBuilder/createDefaultField'

import { applyUiKind, FORM_FIELD_UI_KIND_VALUES, FormFieldUiKindEnum, uiKindForField } from './formFieldUiKind'

describe('formFieldUiKind', () => {
  it.each(FORM_FIELD_UI_KIND_VALUES)('round-trips the %s builder kind', (kind) => {
    expect(uiKindForField(createDefaultField(kind))).toBe(kind)
  })

  it('defaults a text field without display to the single-line UI kind', () => {
    expect(uiKindForField({ type: FormFieldTypeEnum.TEXT, value_name: 'name', label: 'Name' })).toBe(
      FormFieldUiKindEnum.TEXT
    )
  })

  it.each([
    [FormFieldUiKindEnum.TEXT, FormFieldDisplayEnum.SINGLE_LINE],
    [FormFieldUiKindEnum.TEXTAREA, FormFieldDisplayEnum.MULTI_LINE],
    [FormFieldUiKindEnum.MASKED_TEXT, FormFieldDisplayEnum.MASKED],
  ] as const)('converts %s to the API text display value', (kind, display) => {
    const field = applyUiKind({ value_name: 'value', label: 'Value' }, kind)

    expect(field).toMatchObject({ type: FormFieldTypeEnum.TEXT, display })
    expect(uiKindForField(field)).toBe(kind)
  })
})
