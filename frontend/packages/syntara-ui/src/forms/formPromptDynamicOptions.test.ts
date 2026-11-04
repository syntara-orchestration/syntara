import { describe, expect, it } from 'vitest'

import {
  formDefinitionHasUnresolvedDynamicOptions,
  FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_BODY,
  FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_BODY,
} from './formPromptDynamicOptions'

import { FormFieldTypeEnum, parseFormDefinition } from './index'

describe('formPromptDynamicOptions', () => {
  it('detects unresolved dynamic dropdown and multi-select options', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'region',
          label: 'Region',
          options: {
            source: 'dynamic',
            expression: '${trigger.regions}',
            label_key: 'name',
            value_key: 'id',
          },
        },
        {
          type: FormFieldTypeEnum.MULTI_SELECT,
          value_name: 'tags',
          label: 'Tags',
          options: {
            source: 'static',
            values: [{ display_label: 'A', value: 'a' }],
          },
        },
      ],
    })

    expect(formDefinitionHasUnresolvedDynamicOptions(definition)).toBe(true)
  })

  it('treats runtime-resolved options as ready for responders', () => {
    const definition = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'region',
          label: 'Region',
          options: {
            source: 'dynamic_resolved',
            values: [{ display_label: 'US East', value: 'use1' }],
          },
        },
      ],
    })

    expect(formDefinitionHasUnresolvedDynamicOptions(definition)).toBe(false)
  })

  it('exports non-empty alert copy for responder and preview surfaces', () => {
    expect(FORM_PROMPT_UNRESOLVED_DYNAMIC_OPTIONS_ALERT_BODY.length).toBeGreaterThan(20)
    expect(FORM_PROMPT_PREVIEW_DYNAMIC_OPTIONS_ALERT_BODY.length).toBeGreaterThan(20)
  })
})
