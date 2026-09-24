import type { Activity, FormDefinition } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { FormPromptFormSubmitData } from '../node-forms/FormPromptNodeForm'
import { FormPromptNodeForm } from '../node-forms/FormPromptNodeForm'
import type { FormPromptFormData } from '../node-forms/formPromptNodeFormSchema'
import { persistNodeSettings } from '../node-forms/shared/nodeSettingsSchema'
import { buildFormPromptActivityParameters } from '../utils/formPromptActivityParameters'
import { formPromptFallbackDecisionFromBehavior } from '../utils/formPromptFallbackBehavior'

type FormPromptNodeDetailsProps = {
  taskData: Activity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

export function FormPromptNodeDetails({
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
}: Readonly<FormPromptNodeDetailsProps>) {
  const { showError } = useAlerts()
  const updateActivity = useWorkflowStore((state) => state.updateActivity)

  const parameters = (taskData.parameters ?? {}) as {
    message?: string | null
    form_definition?: FormDefinition
    responder_users?: string[]
    responder_groups?: string[]
    response_window?: number | null
    fallback_decision?: 'submit' | 'fallback' | null
    fallback_behavior?: 'fail' | 'fallback' | null
    submit_label?: string | null
    success_message?: string | null
    timezone?: string | null
    css_override?: string | null
  }

  const initialData: Partial<FormPromptFormSubmitData> = {
    name: taskData.name,
    message: parameters.message,
    form_definition: parameters.form_definition as FormPromptFormData['form_definition'],
    responder_users: parameters.responder_users,
    responder_groups: parameters.responder_groups,
    response_window: parameters.response_window,
    fallback_decision:
      parameters.fallback_decision ?? formPromptFallbackDecisionFromBehavior(parameters.fallback_behavior ?? undefined),
    submit_label: parameters.submit_label,
    success_message: parameters.success_message,
    timezone: parameters.timezone,
    css_override: parameters.css_override,
    settings: taskData.settings,
  }

  const handleSubmit = (data: FormPromptFormSubmitData) => {
    try {
      updateActivity(nodeId, {
        name: data.name,
        parameters: buildFormPromptActivityParameters(data),
        settings: persistNodeSettings(data.settings),
      } as Partial<Activity>)
      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update form step',
      })
    }
  }

  const formStateKey = [
    nodeId,
    taskData.settings?.continue_on_failure ?? 'default',
    parameters.fallback_decision ?? '',
  ].join(':')

  return (
    <FormPromptNodeForm
      key={formStateKey}
      onSubmit={handleSubmit}
      initialData={initialData}
      onHeaderContentChange={onHeaderContentChange}
      projectId={projectId}
    />
  )
}
