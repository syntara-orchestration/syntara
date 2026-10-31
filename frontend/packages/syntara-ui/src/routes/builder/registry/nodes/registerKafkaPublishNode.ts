import { RhUiPlugFillIcon } from '@patternfly/react-icons'
import { ActivityTypeEnum } from '@syntara/contracts'

import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { buildKafkaPublishParameters, type KafkaPublishFormData } from '../../node-forms/kafkaPublishFormSchema'
import { KafkaPublishNodeForm } from '../../node-forms/KafkaPublishNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { NodeRegistry } from '../NodeRegistry'

export default function registerKafkaPublishNode() {
  NodeRegistry.register<KafkaPublishFormData>({
    id: ActivityTypeEnum.KAFKA_PUBLISH,
    label: 'Kafka Publish',
    icon: RhUiPlugFillIcon,
    category: 'action',
    description: 'Publish a JSON message to a Kafka topic.',
    keywords: ['kafka', 'publish', 'message', 'json'],
    order: 35,
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
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Failed to add Kafka Publish')
      }
    },
  })
}
