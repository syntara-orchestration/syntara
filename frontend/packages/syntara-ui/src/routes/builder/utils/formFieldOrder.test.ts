import { ActivityTypeEnum, FormFieldTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { buildTriggerNodeId } from '../../../utils/triggerNodeIds'

import { buildFormFieldOrderMap, formFieldOrderFromParameters, orderFormActivityData } from './formFieldOrder'

const fieldOrder = ['deployment_name', 'environment', 'id']

describe('formFieldOrderFromParameters', () => {
  it('reads string value names without validating other field properties', () => {
    const parameters = {
      form_definition: {
        fields: [
          { value_name: 'deployment_name', type: FormFieldTypeEnum.TEXT },
          { value_name: 'environment', type: 'new_backend_field_type' },
          { value_name: 'id', type: FormFieldTypeEnum.NUMBER },
        ],
      },
    }

    expect(formFieldOrderFromParameters(parameters)).toEqual(fieldOrder)
  })

  it.each([
    ['missing parameters', undefined],
    ['missing form definition', {}],
    ['malformed form definition', { form_definition: { fields: 'invalid' } }],
    ['empty fields', { form_definition: { fields: [] } }],
    ['fields without names', { form_definition: { fields: [{ type: FormFieldTypeEnum.TEXT }] } }],
    ['partly malformed fields', { form_definition: { fields: [{ value_name: 'known' }, null] } }],
  ])('returns undefined for %s', (_label, parameters) => {
    expect(formFieldOrderFromParameters(parameters)).toBeUndefined()
  })
})

describe('buildFormFieldOrderMap', () => {
  it('maps form nodes and registers form triggers by definition and canvas IDs', () => {
    const workflow = {
      nodes: [
        {
          id: 'prompt-1',
          type: ActivityTypeEnum.FORM_PROMPT,
          parameters: { form_definition: { fields: fieldOrder.map((value_name) => ({ value_name })) } },
        },
        { id: 'script-1', type: ActivityTypeEnum.SCRIPT, parameters: {} },
      ],
      triggers: [
        { id: 'manual-1', type: TriggerTypeEnum.MANUAL_TRIGGER, parameters: {} },
        {
          id: 'form-trigger-1',
          type: TriggerTypeEnum.FORM_TRIGGER,
          parameters: { form_definition: { fields: fieldOrder.map((value_name) => ({ value_name })) } },
        },
      ],
    }

    const result = buildFormFieldOrderMap(workflow)

    expect(result.get('prompt-1')).toEqual(fieldOrder)
    expect(result.get('form-trigger-1')).toEqual(fieldOrder)
    expect(result.get(buildTriggerNodeId(1))).toEqual(fieldOrder)
    expect(result.has('script-1')).toBe(false)
    expect(result.has(buildTriggerNodeId(0))).toBe(false)
  })

  it('returns an empty map for malformed workflow definitions', () => {
    expect(buildFormFieldOrderMap(null)).toEqual(new Map())
    expect(buildFormFieldOrderMap({ nodes: 'invalid', triggers: null })).toEqual(new Map())
  })
})

describe('orderFormActivityData', () => {
  it('reorders flat form-trigger input data', () => {
    const data = { id: '42', environment: 'stage', deployment_name: 'blue' }

    const ordered = orderFormActivityData(data, TriggerTypeEnum.FORM_TRIGGER, fieldOrder, 'input')

    expect(Object.keys(ordered as Record<string, unknown>)).toEqual(fieldOrder)
    expect(ordered).toEqual({ deployment_name: 'blue', environment: 'stage', id: '42' })
  })

  it('keeps an object-valued response_data form field flat in trigger input', () => {
    const dateValue = { date: '2026-11-19', timezone: 'UTC' }
    const data = { id: '42', response_data: dateValue, deployment_name: 'blue' }

    const ordered = orderFormActivityData(
      data,
      TriggerTypeEnum.FORM_TRIGGER,
      ['deployment_name', 'response_data', 'id'],
      'input'
    )

    expect(Object.keys(ordered)).toEqual(['deployment_name', 'response_data', 'id'])
    expect(ordered.response_data).toBe(dateValue)
  })

  it('reorders response_data inside form-trigger output data', () => {
    const data = { response_data: { id: '42', environment: 'stage', deployment_name: 'blue' } }

    const ordered = orderFormActivityData(data, TriggerTypeEnum.FORM_TRIGGER, fieldOrder, 'output')

    expect(Object.keys(ordered.response_data)).toEqual(fieldOrder)
  })

  it('leaves malformed trigger response_data untouched', () => {
    const data = { response_data: ['invalid'] }

    expect(orderFormActivityData(data, TriggerTypeEnum.FORM_TRIGGER, fieldOrder, 'output')).toBe(data)
  })

  it('reorders only response_data for form prompts', () => {
    const data = {
      status: 'submitted',
      outcome: 'success',
      response_data: { id: '42', environment: 'stage', deployment_name: 'blue' },
      responded_by: 'user@example.com',
    }

    const ordered = orderFormActivityData(data, ActivityTypeEnum.FORM_PROMPT, fieldOrder, 'output')

    expect(Object.keys(ordered)).toEqual(['status', 'outcome', 'response_data', 'responded_by'])
    expect(Object.keys(ordered.response_data)).toEqual(fieldOrder)
    expect(ordered.status).toBe('submitted')
    expect(ordered.outcome).toBe('success')
    expect(ordered.responded_by).toBe('user@example.com')
  })

  it('leaves form prompt parameters and non-form data untouched', () => {
    const parameters = { message: 'Complete the form', form_definition: { fields: [] } }
    const genericData = { id: '42', environment: 'stage' }

    expect(orderFormActivityData(parameters, ActivityTypeEnum.FORM_PROMPT, fieldOrder, 'input')).toBe(parameters)
    expect(orderFormActivityData(genericData, ActivityTypeEnum.SCRIPT, fieldOrder, 'output')).toBe(genericData)
  })

  it('passes malformed values and missing ordering through unchanged', () => {
    const values = [1, 2]
    const record = { id: '42' }

    expect(orderFormActivityData(values, TriggerTypeEnum.FORM_TRIGGER, fieldOrder, 'input')).toBe(values)
    expect(orderFormActivityData('scalar', TriggerTypeEnum.FORM_TRIGGER, fieldOrder, 'input')).toBe('scalar')
    expect(orderFormActivityData(record, TriggerTypeEnum.FORM_TRIGGER, undefined, 'input')).toBe(record)
  })
})
