import { ActivityTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KafkaIcon from '../../../../assets/kafka.svg?react'
import { RegistryNodeId } from '../../../../constants'
import { NodeRegistry } from '../NodeRegistry'

import registerKafkaPublishNode from './registerKafkaPublishNode'

const { addActivity } = vi.hoisted(() => ({ addActivity: vi.fn() }))
vi.mock('../../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: { getState: () => ({ addActivity, currentWorkflow: null }) },
}))

describe('Kafka Publish registration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    NodeRegistry.unregister(ActivityTypeEnum.KAFKA_PUBLISH)
  })

  it('places Kafka Publish under Action with its own logo and description', () => {
    registerKafkaPublishNode()

    expect(NodeRegistry.get(ActivityTypeEnum.KAFKA_PUBLISH)).toMatchObject({
      parentId: RegistryNodeId.ACTION,
      icon: KafkaIcon,
      description: 'Publish a structured message to a Kafka topic.',
      order: 0,
    })
  })

  it('adds a configured action with native JSON and the normal retry settings', () => {
    registerKafkaPublishNode()
    const registration = NodeRegistry.get(ActivityTypeEnum.KAFKA_PUBLISH)
    const onSuccess = vi.fn()
    const onError = vi.fn()
    expect(registration?.category).toBe('action')
    registration?.onSubmit(
      {
        name: 'Publish outcome',
        integration_id: '11111111-1111-4111-8111-111111111111',
        credential_id: '22222222-2222-4222-8222-222222222222',
        connection_ready: true,
        topic: 'outcomes',
        payload: 'false',
        key: { encoding: 'null', value: '' },
        headers_mode: 'entries',
        headers: [],
        headers_template: '',
        settings: { retry_policy: { max_retries: 0 } },
      },
      onSuccess,
      onError
    )
    const added: unknown = addActivity.mock.calls[0]?.[0]
    expect(added).toMatchObject({
      type: ActivityTypeEnum.KAFKA_PUBLISH,
      parameters: { topic: 'outcomes', payload: false, key: null, headers: [] },
      settings: { retry_policy: { max_retries: 0 } },
    })
    expect(onSuccess).toHaveBeenCalledWith(expect.any(String))
    expect(onError).not.toHaveBeenCalled()
  })

  it.each([false, true])(
    'persists an unfinished JSON draft or sanitizes a persistence error: %s',
    (persistenceFails) => {
      registerKafkaPublishNode()
      const onError = vi.fn()
      const onSuccess = vi.fn()
      if (persistenceFails)
        addActivity.mockImplementationOnce(() => {
          throw new Error('sensitive diagnostic')
        })
      NodeRegistry.get(ActivityTypeEnum.KAFKA_PUBLISH)?.onSubmit(
        {
          name: 'Publish outcome',
          integration_id: '11111111-1111-4111-8111-111111111111',
          credential_id: '22222222-2222-4222-8222-222222222222',
          connection_ready: true,
          topic: 'outcomes',
          payload: 'sensitive-message-data is not JSON',
          key: { encoding: 'null', value: '' },
          headers_mode: 'entries',
          headers: [],
          headers_template: '',
          settings: {},
        },
        onSuccess,
        onError
      )
      if (persistenceFails) {
        expect(onError).toHaveBeenCalledWith('Failed to add Kafka Publish. Check the action configuration.')
        expect(onSuccess).not.toHaveBeenCalled()
        return
      }
      const draft: unknown = addActivity.mock.calls[0]?.[0]
      expect(draft).toMatchObject({
        parameters: { payload: undefined },
        metadata: { __kafkaPublishPayloadDraft: 'sensitive-message-data is not JSON' },
      })
      expect(onSuccess).toHaveBeenCalledOnce()
      expect(onError).not.toHaveBeenCalled()
    }
  )
})
