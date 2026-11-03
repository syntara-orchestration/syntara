import { ActivityTypeEnum, type Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { SynErrorState } from '../../../components/states/SynErrorState'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import {
  buildKafkaPublishParameters,
  kafkaPublishInitialFields,
  kafkaPublishParametersSchema,
} from '../node-forms/kafkaPublishFormSchema'
import { KafkaPublishNodeForm } from '../node-forms/KafkaPublishNodeForm'

export function KafkaPublishNodeDetails({
  taskData,
  onClose,
  onHeaderContentChange,
  projectId,
}: Readonly<{
  taskData: Activity
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}>) {
  const { updateActivity } = useWorkflowStoreActions()
  const parameters = kafkaPublishParametersSchema.safeParse(taskData.parameters)
  if (!parameters.success) {
    return (
      <SynErrorState
        title="Invalid Kafka Publish configuration"
        message="The saved parameters do not match the Kafka Publish contract. Correct the configuration in the workflow definition."
      />
    )
  }
  return (
    <KafkaPublishNodeForm
      key={taskData.id}
      projectId={projectId}
      onHeaderContentChange={onHeaderContentChange}
      initialData={{
        name: taskData.name ?? '',
        ...kafkaPublishInitialFields(parameters.data),
        settings: taskData.settings ?? {},
      }}
      onSubmit={(data) => {
        updateActivity(taskData.id, {
          ...taskData,
          type: ActivityTypeEnum.KAFKA_PUBLISH,
          name: data.name,
          parameters: buildKafkaPublishParameters(data),
          settings: data.settings,
        })
        onClose()
      }}
    />
  )
}
