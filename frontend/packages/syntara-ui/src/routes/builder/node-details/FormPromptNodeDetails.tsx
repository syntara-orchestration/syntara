import type { Activity, FormDefinition } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { prepareFormDefinitionForCommit, safeParseFormDefinition } from '../../../forms'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { FormPromptFormSubmitData } from '../node-forms/FormPromptNodeForm'
import { FormPromptNodeForm } from '../node-forms/FormPromptNodeForm'
import { formPromptStoredParametersSchema } from '../node-forms/formPromptNodeFormSchema'
import { persistNodeSettings } from '../node-forms/shared/nodeSettingsSchema'
import { buildFormPromptActivityParameters } from '../utils/formPromptActivityParameters'
import { formPromptFallbackDecisionFromBehavior } from '../utils/formPromptFallbackBehavior'

function readStoredFormDefinition(rawParameters: unknown): FormDefinition | undefined {
  if (typeof rawParameters !== 'object' || rawParameters === null) {
    return undefined
  }
  const raw = (rawParameters as { form_definition?: unknown }).form_definition
  if (typeof raw !== 'object' || raw === null || !('fields' in raw)) {
    return undefined
  }
  const prepared = prepareFormDefinitionForCommit(raw as FormDefinition)
  const parsed = safeParseFormDefinition(prepared)
  return parsed.success ? parsed.data : undefined
}

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

  const rawParameters = taskData.parameters ?? {}
  const parsedParameters = formPromptStoredParametersSchema.safeParse(rawParameters)
  const parameters = parsedParameters.success ? parsedParameters.data : {}
  const storedFormDefinition = parameters.form_definition ?? readStoredFormDefinition(rawParameters)

  const initialData: Partial<FormPromptFormSubmitData> = {
    name: taskData.name,
    message:
      parameters.message ??
      (typeof rawParameters === 'object' && rawParameters !== null
        ? (rawParameters as { message?: string }).message
        : undefined),
    form_definition: storedFormDefinition,
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
      })
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
