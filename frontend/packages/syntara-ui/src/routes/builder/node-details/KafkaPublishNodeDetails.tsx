import { ActivityTypeEnum, type Activity } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import { buildKafkaPublishParameters } from '../node-forms/kafkaPublishFormSchema'
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
  const parameters = taskData.parameters
  return (
    <KafkaPublishNodeForm
      key={taskData.id}
      projectId={projectId}
      onHeaderContentChange={onHeaderContentChange}
      initialData={{
        name: taskData.name ?? '',
        integration_id: typeof parameters.integration_id === 'string' ? parameters.integration_id : '',
        credential_id: typeof parameters.credential_id === 'string' ? parameters.credential_id : '',
        topic: typeof parameters.topic === 'string' ? parameters.topic : '',
        payload: JSON.stringify(parameters.payload, null, 2),
        key: parameters.key == null ? '' : JSON.stringify(parameters.key, null, 2),
        headers: JSON.stringify(parameters.headers ?? [], null, 2),
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
