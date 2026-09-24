import { TriggerTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RegistryNodeId } from '../../../../constants'
import {
  createEdaTrigger,
  createScheduledTrigger,
  createWebhookTrigger,
  useWorkflowStore,
} from '../../../../stores/useWorkflowStore'
import { NodeRegistry } from '../NodeRegistry'

import registerTriggerNode from './registerTriggerNode'

vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(() => ({
      addTrigger: vi.fn(),
    })),
  },
  createManualTrigger: vi.fn((id: string, _: unknown, name: string) => ({
    id,
    name,
    type: TriggerTypeEnum.MANUAL_TRIGGER,
  })),
  createScheduledTrigger: vi.fn((id: string) => ({
    id,
    type: TriggerTypeEnum.SCHEDULED,
  })),
  createWebhookTrigger: vi.fn(({ id }: { id: string }) => ({
    id,
    type: TriggerTypeEnum.WEBHOOK_TRIGGER,
  })),
  createEdaTrigger: vi.fn(({ id }: { id: string }) => ({
    id,
    type: TriggerTypeEnum.EDA_TRIGGER,
  })),
}))

vi.mock('../../../../utils/jsonSafeParse', () => ({
  parseJsonSchema: vi.fn((schema: string | undefined) => (schema?.trim() ? { type: 'object' } : undefined)),
}))

vi.mock('../../../../utils/webhookPath', () => ({
  normalizeWebhookPath: vi.fn((path: string) => path),
}))

describe('registerTriggerNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    NodeRegistry.unregister(RegistryNodeId.TRIGGER)
  })

  it('registers the Trigger step type in the NodeRegistry', () => {
    registerTriggerNode()

    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    expect(registration).toBeDefined()
    expect(registration?.id).toBe(RegistryNodeId.TRIGGER)
    expect(registration?.label).toBe('Triggers')
    expect(registration?.category).toBe('trigger')
    expect(registration?.description).toBe('Start workflow execution with manual, scheduled, or event triggers')
  })

  it('registers with correct order', () => {
    registerTriggerNode()

    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    expect(registration?.order).toBe(100)
  })

  it('registers with searchable keywords', () => {
    registerTriggerNode()

    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    expect(registration?.keywords).toEqual(expect.arrayContaining(['start', 'manual', 'schedule', 'event', 'webhook']))
  })

  it('includes four subtypes: manual, scheduled, webhook, and EDA', () => {
    registerTriggerNode()

    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    expect(registration?.subtypes).toHaveLength(4)

    const manual = registration?.subtypes?.find((s) => s.id === RegistryNodeId.TRIGGER_MANUAL)
    expect(manual).toBeDefined()
    expect(manual?.label).toBe('Manual trigger')
    expect(manual?.initialData).toEqual({ triggerType: TriggerTypeEnum.MANUAL_TRIGGER })

    const scheduled = registration?.subtypes?.find((s) => s.id === RegistryNodeId.TRIGGER_SCHEDULED)
    expect(scheduled).toBeDefined()
    expect(scheduled?.label).toBe('Schedule trigger')
    expect(scheduled?.initialData).toEqual({ triggerType: TriggerTypeEnum.SCHEDULED })

    const webhook = registration?.subtypes?.find((s) => s.id === RegistryNodeId.TRIGGER_WEBHOOK)
    expect(webhook).toBeDefined()
    expect(webhook?.label).toBe('Webhook trigger')

    const eda = registration?.subtypes?.find((s) => s.id === RegistryNodeId.TRIGGER_EDA)
    expect(eda).toBeDefined()
    expect(eda?.label).toBe('Event-Driven Ansible trigger')
    expect(eda?.initialData).toEqual({ triggerType: TriggerTypeEnum.EDA_TRIGGER })
  })

  it('onSubmit creates a manual trigger and calls onSuccess', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      { name: 'My Trigger', triggerType: TriggerTypeEnum.MANUAL_TRIGGER, inputSchema: undefined },
      onSuccess,
      onError
    )

    expect(mockAddTrigger).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit creates a scheduled trigger and calls onSuccess', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Daily Run',
        triggerType: TriggerTypeEnum.SCHEDULED,
        scheduleType: 'cron',
        cron: '0 9 * * *',
        timezone: 'UTC',
        interval: undefined,
      },
      onSuccess,
      onError
    )

    expect(mockAddTrigger).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('defaults scheduleType to interval when omitted', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'No Schedule Type',
        triggerType: TriggerTypeEnum.SCHEDULED,
        interval: '30m',
      },
      onSuccess,
      onError
    )

    expect(vi.mocked(createScheduledTrigger)).toHaveBeenCalledWith(
      expect.any(String),
      'interval',
      expect.objectContaining({ interval: '30m' }),
      expect.any(String)
    )
    expect(onSuccess).toHaveBeenCalled()
  })

  it('defaults webhookPath to empty string when omitted', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Webhook no path',
        triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
      },
      onSuccess,
      onError
    )

    const [webhookArgs] = vi.mocked(createWebhookTrigger).mock.calls[0] ?? []
    expect(webhookArgs).toMatchObject({
      webhookPath: '',
      inputSchema: undefined,
      authorizedServiceAccountIds: undefined,
    })
    expect(typeof webhookArgs?.id).toBe('string')
    expect(typeof webhookArgs?.name).toBe('string')
    expect(onSuccess).toHaveBeenCalled()
  })

  it('onSubmit creates a webhook trigger and calls onSuccess', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit(
      {
        name: 'Webhook',
        triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
        webhookPath: '/hooks/deploy',
        inputSchema: undefined,
      },
      onSuccess,
      onError
    )

    expect(mockAddTrigger).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('passes authorizedServiceAccountIds to createWebhookTrigger (regression: AAP-84946)', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const serviceAccountIds = ['sa-id-1', 'sa-id-2']
    registration?.onSubmit(
      {
        name: 'Webhook with SA',
        triggerType: TriggerTypeEnum.WEBHOOK_TRIGGER,
        webhookPath: '/hooks/deploy',
        inputSchema: undefined,
        authorizedServiceAccountIds: serviceAccountIds,
      },
      onSuccess,
      onError
    )

    const [webhookArgs] = vi.mocked(createWebhookTrigger).mock.calls[0] ?? []
    expect(webhookArgs).toMatchObject({
      webhookPath: '/hooks/deploy',
      inputSchema: undefined,
      authorizedServiceAccountIds: serviceAccountIds,
    })
    expect(typeof webhookArgs?.id).toBe('string')
    expect(typeof webhookArgs?.name).toBe('string')
    expect(onSuccess).toHaveBeenCalled()
  })

  it('passes authorizedServiceAccountIds to createEdaTrigger (regression: AAP-84946)', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    const serviceAccountIds = ['sa-id-3']
    registration?.onSubmit(
      {
        name: 'EDA with SA',
        triggerType: TriggerTypeEnum.EDA_TRIGGER,
        webhookPath: '/eda/events',
        inputSchema: undefined,
        authorizedServiceAccountIds: serviceAccountIds,
      },
      onSuccess,
      onError
    )

    const [edaArgs] = vi.mocked(createEdaTrigger).mock.calls[0] ?? []
    expect(edaArgs).toMatchObject({
      webhookPath: '/eda/events',
      inputSchema: undefined,
      authorizedServiceAccountIds: serviceAccountIds,
    })
    expect(typeof edaArgs?.id).toBe('string')
    expect(typeof edaArgs?.name).toBe('string')
    expect(onSuccess).toHaveBeenCalled()
  })

  it('creates a manual trigger when trigger type is unknown', () => {
    const mockAddTrigger = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: mockAddTrigger,
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({ name: 'Bad', triggerType: 'unknown_type' as never }, onSuccess, onError)

    expect(mockAddTrigger).toHaveBeenCalled()
    expect(onSuccess).toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
  })

  it('onSubmit handles thrown errors and calls onError', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: vi.fn(() => {
        throw new Error('Store error')
      }),
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({ name: 'Crash', triggerType: TriggerTypeEnum.MANUAL_TRIGGER }, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('Store error')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('onSubmit handles non-Error throws with generic message', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      addTrigger: vi.fn(() => {
        throw Object.create(null) as Error
      }),
    } as never)

    registerTriggerNode()
    const registration = NodeRegistry.get(RegistryNodeId.TRIGGER)
    const onSuccess = vi.fn()
    const onError = vi.fn()

    registration?.onSubmit({ name: 'Crash', triggerType: TriggerTypeEnum.MANUAL_TRIGGER }, onSuccess, onError)

    expect(onError).toHaveBeenCalledWith('Failed to add trigger')
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
