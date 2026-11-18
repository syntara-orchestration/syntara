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
