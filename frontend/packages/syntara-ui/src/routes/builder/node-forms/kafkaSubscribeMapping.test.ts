import { TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { parseImportedDefinition } from '../utils/parseImportedDefinition'
import { buildWorkflowDefinition } from '../utils/workflowDefinitionBuilder'

import {
  buildKafkaSubscribeTrigger,
  kafkaSubscribeFormDefaults,
  kafkaSubscribeParameters,
  hasKafkaFilterExpression,
} from './kafkaSubscribeMapping'
import { triggerFormSchema } from './triggerFormSchema'

const integrationId = '11111111-1111-4111-8111-111111111111'
const credentialId = '22222222-2222-4222-8222-222222222222'
const data = {
  triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE,
  integrationId,
  runtimeCredentialId: credentialId,
  topic: 'orders.created',
}

describe('Kafka Subscribe configuration', () => {
  it('round-trips partial consumption settings and exact CEL through export/import and unrelated edits', () => {
    const expression = '  true\n && (true || false)  '
    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', {
      ...data,
      filterExpression: expression,
      kafkaStart: { added_partition_position: 'latest' },
      kafkaGroupId: 'orders.group_1-2',
    })
    const exported = buildWorkflowDefinition({
      workflowName: 'Orders',
      workflowDescription: '',
      activities: [],
      triggers: [trigger],
      edges: [],
    })
    const imported = parseImportedDefinition(exported).workflowDef.triggers?.[0]
    if (!imported) throw new Error('Kafka trigger was discarded')
    const reopened = kafkaSubscribeFormDefaults(imported)
    const updated = buildKafkaSubscribeTrigger(
      'subscribe',
      'Renamed',
      { ...reopened, inputSchema: '{"type":"object"}' },
      imported
    )
    expect(updated.parameters).toMatchObject({
      start: { added_partition_position: 'latest' },
      group_id: 'orders.group_1-2',
      filter: { expression },
      input_schema: { type: 'object' },
    })
    expect(updated.parameters?.start).not.toHaveProperty('position')
    expect(updated.parameters?.start).not.toHaveProperty('offset_gap_policy')
    expect(kafkaSubscribeParameters(reopened)).toMatchObject({
      start: { added_partition_position: 'latest' },
      group_id: 'orders.group_1-2',
    })
  })

  it.each([undefined, null, 'custom-group'])(
    'preserves the same-source group %s on credential-only changes',
    (group) => {
      const previous = {
        id: 'subscribe',
        name: 'Orders',
        type: TriggerTypeEnum.EVENT_SUBSCRIBE,
        parameters: {
          integration_id: integrationId,
          credential_id: credentialId,
          topic: data.topic,
          ...(group !== undefined && { group_id: group }),
          start: {},
        },
      }
      const updated = buildKafkaSubscribeTrigger(
        'subscribe',
        'Orders',
        { ...kafkaSubscribeFormDefaults(previous), runtimeCredentialId: integrationId },
        previous
      )
      expect(updated.parameters?.group_id).toBe(group)
      expect(updated.parameters?.start).toEqual({})
      if (group === undefined) expect(updated.parameters).not.toHaveProperty('group_id')
    }
  )

  it.each([{ topic: 'new-topic' }, { integrationId: credentialId }, { integrationId: '' }, { topic: '' }])(
    'resets a saved group on source change: %j',
    (change) => {
      const previous = buildKafkaSubscribeTrigger('subscribe', 'Orders', {
        ...data,
        kafkaStart: { offset_gap_policy: 'fail' },
        kafkaGroupId: 'saved-group',
      })
      const updated = buildKafkaSubscribeTrigger(
        'subscribe',
        'Orders',
        { ...kafkaSubscribeFormDefaults(previous), ...change, kafkaGroupId: undefined },
        previous
      )
      expect(updated.parameters).toMatchObject({ start: { offset_gap_policy: 'fail' }, group_id: null })
    }
  )

  it('allows an explicitly chosen different group for a replacement source and normalizes a cleared group', () => {
    const previous = buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, kafkaGroupId: 'saved-group' })
    expect(
      buildKafkaSubscribeTrigger(
        'subscribe',
        'Orders',
        { ...data, topic: 'new-topic', kafkaGroupId: 'replacement-group' },
        previous
      ).parameters?.group_id
    ).toBe('replacement-group')
    // Preserve explicit input so publication can report a group-uniqueness conflict.
    expect(
      buildKafkaSubscribeTrigger(
        'subscribe',
        'Orders',
        { ...data, topic: 'new-topic', kafkaGroupId: 'saved-group' },
        previous
      ).parameters?.group_id
    ).toBe('saved-group')
    expect(
      buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, kafkaGroupId: '' }, previous).parameters?.group_id
    ).toBeNull()
  })

  it('does not serialize registration-only undefined policies', () => {
    expect(
      buildKafkaSubscribeTrigger('subscribe', 'Orders', {
        ...data,
        kafkaStart: { position: undefined, added_partition_position: undefined, offset_gap_policy: undefined },
      }).parameters
    ).not.toHaveProperty('start')
  })

  it.each(['bad group', 'group/', 'équipe', '${group}', 'a'.repeat(513), ' '])(
    'rejects an invalid consumer group: %s',
    (kafkaGroupId) => {
      const result = triggerFormSchema.safeParse({ ...data, kafkaGroupId })
      expect(result.success).toBe(false)
      if (!result.success)
        expect(result.error.issues).toContainEqual(expect.objectContaining({ path: ['kafkaGroupId'] }))
    }
  )

  it.each(['', null, undefined, 'group_1-A.B', 'a'.repeat(512)])(
    'accepts a supported optional consumer group: %s',
    (kafkaGroupId) => {
      expect(triggerFormSchema.safeParse({ ...data, kafkaGroupId }).success).toBe(true)
    }
  )

  it.each([
    { position: 'inherit' },
    { added_partition_position: 'inherit' },
    { offset_gap_policy: 'inherit' },
    { position: null },
    { added_partition_position: null },
    { offset_gap_policy: null },
  ])('rejects unsupported reading policies: %j', (kafkaStart) => {
    expect(triggerFormSchema.safeParse({ ...data, kafkaStart }).success).toBe(false)
  })

  it('matches backend Unicode whitespace normalization without dropping a non-empty BOM', () => {
    expect(hasKafkaFilterExpression('\u0085\u001c\u001d\u001e\u001f')).toBe(false)
    expect(hasKafkaFilterExpression('\uFEFF')).toBe(true)
    expect(kafkaSubscribeParameters({ ...data, filterExpression: '\uFEFF' }).filter).toStrictEqual({
      expression: '\uFEFF',
    })
    expect(kafkaSubscribeParameters({ ...data, filterExpression: '\u0085' }).filter).toBeNull()
  })
  it('preserves exact CEL through serialization, reopening and unrelated edits', () => {
    const expression = '  (input.key.kind == "text")\n && (true || false)  '
    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, filterExpression: expression })
    const exported = buildWorkflowDefinition({
      workflowName: 'Orders',
      workflowDescription: '',
      activities: [],
      triggers: [trigger],
      edges: [],
    })
    const imported = parseImportedDefinition(exported)
    const importedTrigger = imported.workflowDef.triggers?.[0]
    expect(importedTrigger).toBeDefined()
    if (!importedTrigger) throw new Error('Kafka trigger was discarded during import')
    const reopened = kafkaSubscribeFormDefaults(importedTrigger)
    expect(reopened.filterExpression).toBe(expression)
    expect(
      buildKafkaSubscribeTrigger('subscribe', 'Renamed', { ...reopened, topic: 'other' }).parameters?.filter
    ).toStrictEqual({ expression })
    expect(kafkaSubscribeParameters(reopened).filter).toStrictEqual({ expression })
  })

  it.each([undefined, '', '  \n\t'])('normalizes an absent or cleared expression to null: %s', (filterExpression) => {
    expect(
      buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, filterExpression }).parameters?.filter
    ).toBeNull()
    expect(kafkaSubscribeParameters({ ...data, filterExpression }).filter).toBeNull()
  })

  it('enforces the expression limit without changing source', () => {
    const filterExpression = ' '.repeat(16_380) + 'true'
    expect(triggerFormSchema.parse({ ...data, filterExpression }).filterExpression).toBe(filterExpression)
    const result = triggerFormSchema.safeParse({ ...data, filterExpression: `${filterExpression} ` })
    expect(result.success).toBe(false)
    if (!result.success)
      expect(result.error.issues).toContainEqual(
        expect.objectContaining({
          path: ['filterExpression'],
          message: 'CEL expression must be 16,384 characters or fewer',
        })
      )
  })
  it('round-trips an incomplete draft without inserting empty strings or runtime-only fields', () => {
    const trigger = buildKafkaSubscribeTrigger('draft', 'Draft', {
      triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE,
      topic: '',
    })
    expect(trigger.parameters).toEqual({ filter: null })
    expect(buildKafkaSubscribeTrigger('draft', 'Draft', kafkaSubscribeFormDefaults(trigger))).toEqual(trigger)
    expect(() => kafkaSubscribeParameters(kafkaSubscribeFormDefaults(trigger))).toThrow()
  })
  it('round-trips the exact topic, literal references and optional payload schema', () => {
    const configured = { ...data, runtimeCredentialId: credentialId, inputSchema: '{"type":"object"}' }
    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', configured)
    const reopened = kafkaSubscribeFormDefaults(trigger)

    expect(trigger.type).toBe('event_subscribe_trigger')
    expect(trigger.parameters).toMatchObject({
      integration_id: integrationId,
      credential_id: credentialId,
      topic: 'orders.created',
      input_schema: { type: 'object' },
    })
    expect(buildKafkaSubscribeTrigger('subscribe', 'Orders', reopened)).toEqual(trigger)
  })

  it('preserves optional schema omission and excludes execution-account and tuning fields', () => {
    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', {
      ...data,
      runtimeCredentialId: credentialId,
      authorizedServiceAccountIds: [credentialId],
    })
    expect(trigger.parameters).not.toHaveProperty('input_schema')
    expect(trigger.parameters).not.toHaveProperty('authorized_service_account_ids')
    expect(trigger.parameters).not.toHaveProperty('service_account_id')
    expect(trigger.parameters).not.toHaveProperty('group_id')
    expect(kafkaSubscribeFormDefaults(trigger).inputSchema).toBeUndefined()
  })

  it('allows an omitted draft credential but requires it for runtime and rejects expressions', () => {
    expect(triggerFormSchema.safeParse({ ...data, runtimeCredentialId: undefined }).success).toBe(true)
    expect(() => kafkaSubscribeParameters({ ...data, runtimeCredentialId: undefined })).toThrow()
    expect(triggerFormSchema.safeParse({ ...data, runtimeCredentialId: '${trigger.credential}' }).success).toBe(false)
    expect(buildKafkaSubscribeTrigger('subscribe', 'Orders', data).parameters).not.toHaveProperty('transport')
  })

  it.each(['.', '..', 'orders.*', 'orders,other', '${trigger.topic}', 'has space', 'a'.repeat(250)])(
    'rejects a non-exact topic: %s',
    (topic) => {
      expect(triggerFormSchema.safeParse({ ...data, topic }).success).toBe(false)
    }
  )

  it.each(['orders', 'orders-1_A.B', 'a'.repeat(249)])('accepts exact topic: %s', (topic) => {
    expect(triggerFormSchema.safeParse({ ...data, topic }).success).toBe(true)
  })

  it.each(['${trigger.integration}', 'not-a-uuid'])('rejects non-literal Integration references: %s', (value) => {
    expect(triggerFormSchema.safeParse({ ...data, integrationId: value }).success).toBe(false)
  })

  it.each(['{', '[]', 'null', '"string"'])('rejects invalid payload schema: %s', (inputSchema) => {
    expect(triggerFormSchema.safeParse({ ...data, inputSchema }).success).toBe(false)
  })
})
