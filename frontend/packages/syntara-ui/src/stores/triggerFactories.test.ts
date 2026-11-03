import { TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import {
  createEdaTrigger,
  createEventTrigger,
  createManualTrigger,
  createScheduledTrigger,
  createWebhookTrigger,
} from './triggerFactories'

describe('triggerFactories', () => {
  describe('createManualTrigger', () => {
    it('creates a manual trigger with defaults', () => {
      const trigger = createManualTrigger('t1')
      expect(trigger).toEqual({
        id: 't1',
        type: TriggerTypeEnum.MANUAL_TRIGGER,
        name: 'Manual Trigger',
        parameters: {},
      })
    })

    it('uses provided name', () => {
      const trigger = createManualTrigger('t1', undefined, 'My Trigger')
      expect(trigger.name).toBe('My Trigger')
    })

    it('includes input_schema when provided', () => {
      const schema = { type: 'object', properties: { x: { type: 'number' } } }
      const trigger = createManualTrigger('t1', undefined, undefined, schema)
      expect(trigger.parameters).toEqual({ input_schema: schema })
    })
  })

  describe('createScheduledTrigger', () => {
    it('creates a cron scheduled trigger', () => {
      const trigger = createScheduledTrigger('t1', 'cron', { cron: '0 9 * * *' })
      expect(trigger).toEqual({
        id: 't1',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Scheduled Trigger',
        parameters: { schedule_type: 'cron', cron: '0 9 * * *' },
      })
    })

    it('creates an interval scheduled trigger with all config options', () => {
      const trigger = createScheduledTrigger(
        't1',
        'interval',
        { interval: 'PT1H', timezone: 'UTC', missed_schedule_policy: 'skip' },
        'Hourly Job'
      )
      expect(trigger).toEqual({
        id: 't1',
        type: TriggerTypeEnum.SCHEDULED,
        name: 'Hourly Job',
        parameters: {
          schedule_type: 'interval',
          interval: 'PT1H',
          timezone: 'UTC',
          missed_schedule_policy: 'skip',
        },
      })
    })

    it('omits empty config values', () => {
      const trigger = createScheduledTrigger('t1', 'interval', {})
      expect(trigger.parameters).toEqual({ schedule_type: 'interval' })
    })
  })

  describe('createEventTrigger', () => {
    it('creates an event trigger with required fields', () => {
      const trigger = createEventTrigger({ id: 't1', source: 'github', eventType: 'push' })
      expect(trigger).toEqual({
        id: 't1',
        type: TriggerTypeEnum.EVENT,
        name: 'Event Trigger',
        parameters: { source: 'github', event_type: 'push' },
      })
    })

    it('includes filter when provided', () => {
      const filter = { branch: 'main' }
      const trigger = createEventTrigger({
        id: 't1',
        source: 'github',
        eventType: 'push',
        filter,
        name: 'Push Trigger',
      })
      expect(trigger.parameters).toEqual({ source: 'github', event_type: 'push', filter })
      expect(trigger.name).toBe('Push Trigger')
    })
  })

  describe('createWebhookTrigger', () => {
    it('creates a webhook trigger with path only', () => {
      const trigger = createWebhookTrigger({ id: 't1', webhookPath: 'my-hook' })
      expect(trigger).toEqual({
        id: 't1',
        type: TriggerTypeEnum.WEBHOOK_TRIGGER,
        name: 'Webhook Trigger',
        parameters: { webhook_path: 'my-hook' },
      })
    })

    it('includes input_schema and authorizedServiceAccountIds', () => {
      const schema = { type: 'object' }
      const trigger = createWebhookTrigger({
        id: 't1',
        webhookPath: 'hook',
        inputSchema: schema,
        name: 'Custom WH',
        authorizedServiceAccountIds: ['sa-1', 'sa-2'],
      })
      expect(trigger.parameters).toEqual({
        webhook_path: 'hook',
        input_schema: schema,
        authorized_service_account_ids: ['sa-1', 'sa-2'],
      })
      expect(trigger.name).toBe('Custom WH')
    })

    it('omits authorized_service_account_ids when array is empty', () => {
      const trigger = createWebhookTrigger({
        id: 't1',
        webhookPath: 'hook',
        inputSchema: undefined,
        name: undefined,
        authorizedServiceAccountIds: [],
      })
      expect(trigger.parameters).toEqual({ webhook_path: 'hook' })
    })
  })

  describe('createEdaTrigger', () => {
    it('creates an EDA trigger with path only', () => {
      const trigger = createEdaTrigger({ id: 't1', webhookPath: 'eda-path' })
      expect(trigger).toEqual({
        id: 't1',
        type: TriggerTypeEnum.EDA_TRIGGER,
        name: 'EDA Trigger',
        parameters: { webhook_path: 'eda-path' },
      })
    })

    it('includes input_schema and authorizedServiceAccountIds', () => {
      const schema = { type: 'object' }
      const trigger = createEdaTrigger({
        id: 't1',
        webhookPath: 'eda',
        inputSchema: schema,
        name: 'My EDA',
        authorizedServiceAccountIds: ['sa-3'],
      })
      expect(trigger.parameters).toEqual({
        webhook_path: 'eda',
        input_schema: schema,
        authorized_service_account_ids: ['sa-3'],
      })
      expect(trigger.name).toBe('My EDA')
    })

    it('omits authorized_service_account_ids when array is empty', () => {
      const trigger = createEdaTrigger({
        id: 't1',
        webhookPath: 'eda',
        inputSchema: undefined,
        name: undefined,
        authorizedServiceAccountIds: [],
      })
      expect(trigger.parameters).toEqual({ webhook_path: 'eda' })
    })
  })
})
