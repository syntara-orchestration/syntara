import { FormFieldTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import {
  createDefaultField,
  createEmptyFormDefinition,
  defaultDynamicOptionsSource,
} from '../../../components/forms/formFieldBuilder/createDefaultField'

import { buildFormTriggerActivityParameters } from './formTriggerActivityParameters'

describe('buildFormTriggerActivityParameters', () => {
  it('omits blank optional strings and trims non-empty values', () => {
    const result = buildFormTriggerActivityParameters({
      form_definition: createEmptyFormDefinition(),
      message: '  Hello  ',
      submit_label: '   ',
      success_message: 'Done',
      css_override: '',
    })

    expect(result).toMatchObject({
      message: 'Hello',
      success_message: 'Done',
    })
    expect(result).not.toHaveProperty('submit_label')
    expect(result).not.toHaveProperty('css_override')
    expect(result.form_definition).toBeDefined()
  })

  it('persists draft form definitions that fail strict validation', () => {
    const result = buildFormTriggerActivityParameters({
      form_definition: { fields: [] },
    })

    expect(result.form_definition).toEqual({ fields: [] })
  })

  it('persists dynamic dropdown options for canvas validation to report', () => {
    const dropdown = {
      ...createDefaultField(FormFieldTypeEnum.DROPDOWN),
      options: {
        ...defaultDynamicOptionsSource(),
        expression: '${trigger.items}',
        label_key: 'name',
        value_key: 'id',
      },
    }

    const result = buildFormTriggerActivityParameters({
      form_definition: { fields: [dropdown] },
    })

    expect((result.form_definition as { fields: unknown[] }).fields).toHaveLength(1)
  })
})
