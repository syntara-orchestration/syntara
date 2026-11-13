import { ActivityTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { getActivityMetadata, type ActivityWithMetadata } from '../../../stores/workflowStoreTypes'
import { kafkaPublishInitialFields, kafkaPublishParametersSchema } from '../node-forms/kafkaPublishFormSchema'

import { convertV2Definition } from './processExistingWorkflow'
import { buildWorkflowDefinition } from './workflowDefinitionBuilder'

function saveNode(activity: ActivityWithMetadata) {
  return buildWorkflowDefinition({
    workflowName: 'Kafka draft',
    workflowDescription: '',
    activities: [activity],
    triggers: [],
    edges: [],
  })
}

describe('Kafka Publish draft persistence', () => {
  it.each(['', '{"result":', '{\n  "result":'])(
    'preserves unfinished payload text through save and reopen: %j',
    (payload) => {
      const saved = saveNode({
        id: 'publish',
        type: ActivityTypeEnum.KAFKA_PUBLISH,
        parameters: { integration_id: '', credential_id: '', topic: '' },
        metadata: { __kafkaPublishPayloadDraft: payload, __customMessage: 'UI only', __isGeneric: true },
      })
      expect(saved.nodes[0]?.metadata).toEqual({ __kafkaPublishPayloadDraft: payload })
      expect(saved.nodes[0]?.parameters).not.toHaveProperty('payload')

      const reopened = convertV2Definition(saved.nodes, [], []).flattenedActivities[0]
      if (!reopened) throw new Error('Saved Kafka Publish node was lost')
      const parameters = kafkaPublishParametersSchema.parse(reopened.parameters)
      expect(kafkaPublishInitialFields(parameters, getActivityMetadata(reopened)).payload).toBe(payload)
    }
  )

  it('omits unrelated UI metadata when saving a configured payload', () => {
    const saved = saveNode({
      id: 'publish',
      type: ActivityTypeEnum.KAFKA_PUBLISH,
      parameters: { payload: null },
      metadata: { __isGeneric: true, __customMessage: 'UI only' },
    })
    expect(saved.nodes[0]?.parameters.payload).toBeNull()
    expect(saved.nodes[0]).not.toHaveProperty('metadata')
  })

  it('does not copy Kafka draft metadata onto other action types', () => {
    const saved = saveNode({
      id: 'script',
      type: ActivityTypeEnum.SCRIPT,
      parameters: { language: 'python', code: 'print("hello")' },
      metadata: { __kafkaPublishPayloadDraft: '{"result":' },
    })
    expect(saved.nodes[0]).not.toHaveProperty('metadata')
  })
})
