import { ActivityTypeEnum, getNodeOutputSchema, TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { getEffectiveOutputSchema, type PreviewFieldDef } from './effectiveOutputSchema'

type FieldFixture = Record<string, unknown>

function formDefinition(...fields: FieldFixture[]) {
  return { fields }
}

function textField(valueName: string, overrides: FieldFixture = {}): FieldFixture {
  return { type: 'text', value_name: valueName, label: `Label ${valueName}`, ...overrides }
}

function formPrompt(form_definition: unknown, id = 'prompt-1') {
  return { id, type: ActivityTypeEnum.FORM_PROMPT, parameters: { form_definition } }
}

function formTrigger(form_definition: unknown, id = 'form-trigger-1') {
  return { id, type: TriggerTypeEnum.FORM_TRIGGER, parameters: { form_definition } }
}

function responseDataChildren(fields: PreviewFieldDef[] | null): PreviewFieldDef[] | undefined {
  return fields?.find((field) => field.name === 'response_data')?.children
}

describe('getEffectiveOutputSchema', () => {
  describe.each([
    ['form prompt', formPrompt],
    ['form trigger', formTrigger],
  ])('%s with a configured form', (_label, buildNode) => {
    it('exposes configured fields as children of response_data', () => {
      const node = buildNode(
        formDefinition(textField('full_name', { help_text: 'Legal name' }), textField('nickname', { required: false }))
      )

      const children = responseDataChildren(getEffectiveOutputSchema(node))

      expect(children).toStrictEqual([
        { name: 'full_name', type: 'string', description: 'Legal name', displayName: 'Label full_name' },
        { name: 'nickname', type: 'string', description: '', displayName: 'Label nickname' },
      ])
    })

    it('keeps the generic metadata fields alongside the configured children', () => {
      const node = buildNode(formDefinition(textField('email_address')))
      const staticNames = (getNodeOutputSchema(node.type) ?? []).map((field) => field.name)

      const fields = getEffectiveOutputSchema(node)

      expect(fields?.map((field) => field.name)).toStrictEqual(staticNames)
      expect(fields?.find((field) => field.name === 'response_data')?.type).toBe('object')
    })

    it('does not add children to fields other than response_data', () => {
      const node = buildNode(formDefinition(textField('only_field')))

      const fields = getEffectiveOutputSchema(node) ?? []

      expect(fields.filter((field) => field.children).map((field) => field.name)).toStrictEqual(['response_data'])
    })
  })

  describe('field output types', () => {
    function typeOf(field: FieldFixture): PreviewFieldDef['type'] | undefined {
      const node = formPrompt(formDefinition({ value_name: 'answer', label: 'Answer', ...field }))
      return responseDataChildren(getEffectiveOutputSchema(node))?.[0]?.type
    }

    it.each([
      ['text', { type: 'text' }, 'string'],
      ['email', { type: 'email' }, 'string'],
      ['number', { type: 'number' }, 'number'],
      ['checkbox', { type: 'checkbox' }, 'boolean'],
      ['date', { type: 'date' }, 'string'],
      ['multi-select with static options', { type: 'multi_select', options: staticOptions() }, 'array'],
      ['multi-select with dynamic options', { type: 'multi_select', options: dynamicOptions() }, 'array'],
      ['dropdown with static options', { type: 'dropdown', options: staticOptions() }, 'string'],
      ['dropdown with dynamic options', { type: 'dropdown', options: dynamicOptions() }, 'unknown'],
    ])('maps %s to %s', (_name, field, expected) => {
      expect(typeOf(field)).toBe(expected)
    })

    it('uses the common value type of resolved dynamic dropdown options', () => {
      const options = { source: 'dynamic_resolved', values: [resolved('One', 1), resolved('Two', 2)] }

      expect(typeOf({ type: 'dropdown', options })).toBe('number')
    })

    it('reports unknown when resolved dynamic options mix value types', () => {
      const options = { source: 'dynamic_resolved', values: [resolved('One', 1), resolved('Two', 'two')] }

      expect(typeOf({ type: 'dropdown', options })).toBe('unknown')
    })
  })

  describe('dynamic options still being configured', () => {
    // The field builder seeds blank expression/label_key/value_key when a field is switched to dynamic options.
    const blankDynamicOptions = { source: 'dynamic', expression: '', label_key: '', value_key: '' }

    it.each([
      ['dropdown', 'unknown'],
      ['multi_select', 'array'],
    ])('keeps every field when a %s has blank dynamic options', (type, expectedType) => {
      const node = formPrompt(
        formDefinition(textField('email'), {
          type,
          value_name: 'region',
          label: 'Region',
          options: blankDynamicOptions,
        })
      )

      const children = responseDataChildren(getEffectiveOutputSchema(node))

      expect(children?.map((field) => [field.name, field.type])).toStrictEqual([
        ['email', 'string'],
        ['region', expectedType],
      ])
    })

    it('still rejects the definition when another field is invalid', () => {
      const node = formPrompt(
        formDefinition(
          { type: 'dropdown', value_name: 'region', label: 'Region', options: blankDynamicOptions },
          { type: 'text', value_name: '1-bad', label: 'Bad' }
        )
      )

      expect(responseDataChildren(getEffectiveOutputSchema(node))).toBeUndefined()
    })
  })

  describe('missing or invalid form definitions', () => {
    it.each([
      ['missing', undefined],
      ['null', null],
      ['not an object', 'not-a-form'],
      ['without fields', {}],
      ['with an empty field list', formDefinition()],
      ['with an invalid field', formDefinition({ type: 'text', value_name: '1-bad', label: 'Bad' })],
      ['with duplicate value names', formDefinition(textField('dup'), textField('dup'))],
    ])('falls back to the generic schema when the definition is %s', (_name, definition) => {
      const node = formPrompt(definition)

      const fields = getEffectiveOutputSchema(node)

      expect(fields).toStrictEqual(getNodeOutputSchema(ActivityTypeEnum.FORM_PROMPT))
      expect(responseDataChildren(fields)).toBeUndefined()
    })

    it('falls back when a form node has no parameters at all', () => {
      const fields = getEffectiveOutputSchema({ id: 'prompt-1', type: ActivityTypeEnum.FORM_PROMPT })

      expect(fields?.map((field) => field.name)).toContain('response_data')
      expect(responseDataChildren(fields)).toBeUndefined()
    })
  })

  describe('isolation', () => {
    it('does not mutate the shared generated schema', () => {
      getEffectiveOutputSchema(formPrompt(formDefinition(textField('leaky'))))

      const shared = getNodeOutputSchema(ActivityTypeEnum.FORM_PROMPT)
      expect(shared?.find((field) => field.name === 'response_data')).not.toHaveProperty('children')
    })

    it('does not leak fields between two differently configured forms', () => {
      const first = getEffectiveOutputSchema(formPrompt(formDefinition(textField('alpha')), 'prompt-a'))
      const second = getEffectiveOutputSchema(formPrompt(formDefinition(textField('beta')), 'prompt-b'))

      expect(responseDataChildren(first)?.map((field) => field.name)).toStrictEqual(['alpha'])
      expect(responseDataChildren(second)?.map((field) => field.name)).toStrictEqual(['beta'])
    })

    it('reflects an edited definition on the next call', () => {
      const before = getEffectiveOutputSchema(formPrompt(formDefinition(textField('old_name'))))
      const after = getEffectiveOutputSchema(formPrompt(formDefinition(textField('new_name'), textField('added'))))

      expect(responseDataChildren(before)?.map((field) => field.name)).toStrictEqual(['old_name'])
      expect(responseDataChildren(after)?.map((field) => field.name)).toStrictEqual(['new_name', 'added'])
    })
  })

  describe('non-form nodes', () => {
    it('returns the generated schema for an activity without adding children', () => {
      const fields = getEffectiveOutputSchema({ id: 'script-1', type: 'script', parameters: { form_definition: {} } })

      expect(fields).toStrictEqual(getNodeOutputSchema('script'))
      expect(fields?.some((field) => field.children)).toBe(false)
    })

    it('returns a copy so callers cannot mutate the generated schema', () => {
      const fields = getEffectiveOutputSchema({ id: 'script-1', type: 'script' })
      const shared = getNodeOutputSchema('script')

      expect(fields).not.toBe(shared)
      expect(fields?.[0]).not.toBe(shared?.[0])
    })

    it('returns null for an unknown node type without a trigger input schema', () => {
      expect(getEffectiveOutputSchema({ id: 'mystery', type: 'unknown_type' })).toBeNull()
    })

    describe('manual trigger input_schema fallback', () => {
      const triggers = [
        {
          id: 'real-trigger-id',
          parameters: { input_schema: { type: 'object', properties: { hostname: { type: 'string' } } } },
        },
      ]

      it('resolves the trigger by its actual id', () => {
        const fields = getEffectiveOutputSchema({ id: 'real-trigger-id', type: 'manual_trigger' }, triggers)

        expect(fields?.map((field) => field.name)).toStrictEqual(['hostname'])
      })

      it('resolves the trigger by its canvas display id', () => {
        const fields = getEffectiveOutputSchema({ id: 'trigger-0', type: 'manual_trigger' }, triggers)

        expect(fields?.map((field) => field.name)).toStrictEqual(['hostname'])
      })

      it('returns null when no trigger matches', () => {
        expect(getEffectiveOutputSchema({ id: 'trigger-5', type: 'manual_trigger' }, triggers)).toBeNull()
      })
    })
  })
})

function staticOptions() {
  return { source: 'static', values: [{ display_label: 'One', value: 'one' }] }
}

function dynamicOptions() {
  return { source: 'dynamic', expression: '${step.items}', label_key: 'name', value_key: 'id' }
}

function resolved(display_label: string, value: string | number | boolean) {
  return { display_label, value }
}
