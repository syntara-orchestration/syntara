import { ActivityTypeEnum } from '@syntara/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
        credential_id: '',
        topic: 'outcomes',
        payload: 'false',
        key: '',
        headers: '[]',
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
})
