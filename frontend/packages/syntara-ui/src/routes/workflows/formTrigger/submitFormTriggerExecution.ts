import { executionsFetchClient } from '../../../client'
import { FormDataValidationError, parseFormValidationProblemDetail, type FormDefinition } from '../../../forms'

type ExecutionProblem = {
  code?: string
  detail?: string
}

function asExecutionProblem(error: unknown): ExecutionProblem | null {
  if (!error || typeof error !== 'object') {
    return null
  }
  const record = error as Record<string, unknown>
  const detail = typeof record.detail === 'string' ? record.detail : undefined
  const code = typeof record.code === 'string' ? record.code : undefined
  if (!detail && !code) {
    return null
  }
  return { detail, code }
}

export type SubmitFormTriggerExecutionOptions = {
  workflowId: string
  triggerNodeId: string
  inputData: Record<string, unknown>
  usePublished?: boolean
  formDefinition: FormDefinition
}

export async function submitFormTriggerExecution({
  workflowId,
  triggerNodeId,
  inputData,
  usePublished = false,
  formDefinition,
}: SubmitFormTriggerExecutionOptions): Promise<string> {
  const { data, error } = await executionsFetchClient.POST('/executions', {
    body: {
      workflow_id: workflowId,
      trigger_node_id: triggerNodeId,
      input_data: inputData,
      ...(usePublished ? { use_published: true } : {}),
    },
  })

  if (error) {
    const problem = asExecutionProblem(error)
    if (problem?.code === 'FORM_VALIDATION_ERROR' && problem.detail) {
      const fieldErrors = parseFormValidationProblemDetail(problem.detail, formDefinition)
      if (fieldErrors.length > 0) {
        throw new FormDataValidationError(fieldErrors)
      }
    }
    throw new Error('Failed to start workflow execution')
  }

  if (!data?.id) {
    throw new Error('Failed to start workflow execution')
  }

  return data.id
}
