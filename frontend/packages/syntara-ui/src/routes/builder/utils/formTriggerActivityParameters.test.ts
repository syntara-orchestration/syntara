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

  it('rejects dynamic dropdown options', () => {
    const dropdown = {
      ...createDefaultField(FormFieldTypeEnum.DROPDOWN),
      options: {
        ...defaultDynamicOptionsSource(),
        expression: '${trigger.items}',
        label_key: 'name',
        value_key: 'id',
      },
    }

    expect(() =>
      buildFormTriggerActivityParameters({
        form_definition: { fields: [dropdown] },
      })
    ).toThrow(/dynamic options are not supported/)
  })

  it('throws when form definition fails validation', () => {
    expect(() =>
      buildFormTriggerActivityParameters({
        form_definition: { fields: [] },
      })
    ).toThrow()
  })
})
