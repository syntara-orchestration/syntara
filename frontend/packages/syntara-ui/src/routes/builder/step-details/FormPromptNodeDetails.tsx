import type { Activity, FormDefinition } from '@syntara/contracts'
import type { ReactNode } from 'react'
import { useEffect, useMemo } from 'react'

import { createEmptyFormDefinition } from '../../../components/forms/formFieldBuilder/createDefaultField'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { FormPromptFormSubmitData } from '../step-forms/FormPromptNodeForm'
import { FormPromptNodeForm } from '../step-forms/FormPromptNodeForm'
import { formPromptStoredParametersSchema } from '../step-forms/formPromptNodeFormSchema'
import { persistStepSettings } from '../step-forms/shared/stepSettingsSchema'
import { isStoredFormDefinitionValid } from '../utils/clearNodeValidationErrors'
import { buildFormPromptActivityParameters } from '../utils/formPromptActivityParameters'
import { formPromptFallbackDecisionFromBehavior } from '../utils/formPromptFallbackBehavior'
import { readDraftFormDefinitionFromParameters, readStoredFormDefinition } from '../utils/readStoredFormDefinition'

type FormPromptNodeDetailsProps = {
  taskData: Activity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
  serverValidationErrors?: ReadonlyArray<{ fieldPath?: string | null; message: string }>
  onFormDefinitionCommitted?: (nodeId: string, formDefinition: FormDefinition) => void
}

export function FormPromptNodeDetails({
  taskData,
  nodeId,
  onClose,
  onHeaderContentChange,
  projectId,
  serverValidationErrors,
  onFormDefinitionCommitted,
}: Readonly<FormPromptNodeDetailsProps>) {
  const { showError } = useAlerts()
  const updateActivity = useWorkflowStore((state) => state.updateActivity)
  const activityParametersFromStore = useWorkflowStore(
    (state) => state.currentWorkflow?.workflow?.activities?.find((activity) => activity.id === nodeId)?.parameters
  )

  const rawParameters = useMemo(
    () => activityParametersFromStore ?? taskData.parameters ?? {},
    [activityParametersFromStore, taskData.parameters]
  )
  const parsedParameters = formPromptStoredParametersSchema.safeParse(rawParameters)
  const parameters = parsedParameters.success ? parsedParameters.data : {}
  const storedFormDefinition: FormDefinition = useMemo(() => {
    return (
      readDraftFormDefinitionFromParameters(rawParameters) ??
      readStoredFormDefinition(rawParameters) ??
      createEmptyFormDefinition()
    )
  }, [rawParameters])

  useEffect(() => {
    if (!isStoredFormDefinitionValid(storedFormDefinition)) {
      return
    }
    // Clear stale verify findings when reopening a step whose saved definition is already valid.
    onFormDefinitionCommitted?.(nodeId, storedFormDefinition)
  }, [nodeId, onFormDefinitionCommitted, storedFormDefinition])

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
    css_override: parameters.css_override,
    settings: taskData.settings,
  }

  const handleSubmit = (data: FormPromptFormSubmitData) => {
    try {
      updateActivity(nodeId, {
        name: data.name,
        parameters: buildFormPromptActivityParameters(data),
        settings: persistStepSettings(data.settings),
      })
      onFormDefinitionCommitted?.(nodeId, data.form_definition)
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
      serverValidationErrors={serverValidationErrors}
    />
  )
}
