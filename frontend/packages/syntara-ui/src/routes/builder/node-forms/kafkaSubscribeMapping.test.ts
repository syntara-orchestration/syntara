import { TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import {
  buildKafkaSubscribeTrigger,
  kafkaSubscribeFormDefaults,
  kafkaSubscribeParameters,
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
  it('round-trips an incomplete draft without inserting empty strings or runtime-only fields', () => {
    const trigger = buildKafkaSubscribeTrigger('draft', 'Draft', {
      triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE,
      topic: '',
    })
    expect(trigger.parameters).toEqual({})
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

  it.each(['orders-reader', null])('preserves hidden reading settings and group %s when renamed', (groupId) => {
    const saved = buildKafkaSubscribeTrigger('subscribe', 'Orders', data)
    const trigger = {
      ...saved,
      parameters: {
        ...saved.parameters,
        start: { offset_gap_policy: 'fail' },
        group_id: groupId,
      },
    }
    const reopened = kafkaSubscribeFormDefaults(trigger)

    const updated = buildKafkaSubscribeTrigger('subscribe', 'Renamed orders', reopened, trigger)

    expect(updated).toStrictEqual({ ...trigger, name: 'Renamed orders' })
  })

  it('preserves omitted consumption controls when editing an older trigger', () => {
    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', data)

    const updated = buildKafkaSubscribeTrigger(
      'subscribe',
      'Renamed orders',
      kafkaSubscribeFormDefaults(trigger),
      trigger
    )

    expect(updated).toStrictEqual({ ...trigger, name: 'Renamed orders' })
  })

  it.each([
    { integrationId, topic: 'orders.v2' },
    { integrationId: '33333333-3333-4333-8333-333333333333', topic: data.topic },
  ])('resets the custom group and preserves reading settings when the source becomes %j', (source) => {
    const saved = buildKafkaSubscribeTrigger('subscribe', 'Orders', data)
    const start = { position: 'earliest', added_partition_position: 'latest', offset_gap_policy: 'fail' }
    const trigger = { ...saved, parameters: { ...saved.parameters, start, group_id: 'orders-reader' } }

    const updated = buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, ...source }, trigger)

    expect(updated.parameters).toStrictEqual({
      integration_id: source.integrationId,
      credential_id: credentialId,
      topic: source.topic,
      start,
      group_id: null,
    })
  })

  it('keeps an omitted group omitted when the source changes', () => {
    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', data)

    const updated = buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, topic: 'orders.v2' }, trigger)

    expect(updated.parameters).toStrictEqual({ ...trigger.parameters, topic: 'orders.v2' })
  })

  it('preserves the group and partial reading settings when only the credential changes', () => {
    const saved = buildKafkaSubscribeTrigger('subscribe', 'Orders', data)
    const start = { offset_gap_policy: 'fail' }
    const trigger = { ...saved, parameters: { ...saved.parameters, start, group_id: 'orders-reader' } }
    const runtimeCredentialId = '33333333-3333-4333-8333-333333333333'

    const updated = buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, runtimeCredentialId }, trigger)

    expect(updated.parameters).toStrictEqual({ ...trigger.parameters, credential_id: runtimeCredentialId })
  })

  it('preserves reading controls while allowing the payload schema to be cleared and excluding unsupported fields', () => {
    const saved = buildKafkaSubscribeTrigger('subscribe', 'Orders', data)
    const start = { position: 'earliest', added_partition_position: 'latest', offset_gap_policy: 'fail' }
    const trigger = {
      ...saved,
      parameters: {
        ...saved.parameters,
        input_schema: { type: 'object' },
        start,
        group_id: 'orders-reader',
        enable_auto_commit: true,
      },
    }

    const updated = buildKafkaSubscribeTrigger('subscribe', 'Orders', { ...data, inputSchema: '' }, trigger)

    expect(updated.parameters).toStrictEqual({ ...saved.parameters, start, group_id: 'orders-reader' })
  })

  it('does not copy parameters from another trigger type when switching to Kafka', () => {
    const previousTrigger = {
      id: 'subscribe',
      type: TriggerTypeEnum.MANUAL_TRIGGER,
      parameters: { start: { position: 'earliest' }, group_id: 'unrelated-group' },
    }

    const trigger = buildKafkaSubscribeTrigger('subscribe', 'Orders', data, previousTrigger)

    expect(trigger).toStrictEqual(buildKafkaSubscribeTrigger('subscribe', 'Orders', data))
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
