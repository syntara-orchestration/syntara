import { ActivityTypeEnum } from '@syntara/contracts'

import KafkaIcon from '../../../../assets/kafka.svg?react'
import { RegistryNodeId } from '../../../../constants'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { buildKafkaPublishParameters, type KafkaPublishFormData } from '../../node-forms/kafkaPublishFormSchema'
import { KafkaPublishNodeForm } from '../../node-forms/KafkaPublishNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { NodeRegistry } from '../NodeRegistry'

export default function registerKafkaPublishNode() {
  NodeRegistry.register<KafkaPublishFormData>({
    id: ActivityTypeEnum.KAFKA_PUBLISH,
    label: 'Kafka Publish',
    icon: KafkaIcon,
    category: 'action',
    parentId: RegistryNodeId.ACTION,
    description: 'Publish a structured message to a Kafka topic.',
    keywords: ['kafka', 'publish', 'message', 'json'],
    order: 0,
    formComponent: KafkaPublishNodeForm,
    enabled: true,
    onSubmit: (data, onSuccess, onError) => {
      try {
        const { activityId, activity } = buildNamedActivity('Publish to Kafka', data.name, (id, name) => ({
          id,
          name,
          type: ActivityTypeEnum.KAFKA_PUBLISH,
          parameters: buildKafkaPublishParameters(data),
          settings: data.settings,
        }))
        useWorkflowStore.getState().addActivity(activity)
        onSuccess(activityId)
      } catch {
        onError('Failed to add Kafka Publish. Check the action configuration.')
      }
    },
  })
}
