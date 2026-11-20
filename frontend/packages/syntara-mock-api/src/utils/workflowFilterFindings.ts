import type { WorkflowAPI } from '@syntara/contracts'

type Finding = WorkflowAPI.components['schemas']['ValidationFinding']

/** Canned compiler finding shared by workflow Save and Verify; this is not a CEL engine. */
export function workflowFilterFindings(definition: unknown): Finding[] {
  if (
    !definition ||
    typeof definition !== 'object' ||
    !('triggers' in definition) ||
    !Array.isArray(definition.triggers)
  )
    return []
  return definition.triggers.flatMap((trigger: unknown): Finding[] => {
    if (
      !trigger ||
      typeof trigger !== 'object' ||
      !('type' in trigger) ||
      trigger.type !== 'event_subscribe_trigger' ||
      !('parameters' in trigger)
    )
      return []
    const parameters: unknown = trigger.parameters
    if (!parameters || typeof parameters !== 'object' || !('filter' in parameters)) return []
    const filter: unknown = parameters.filter
    if (
      !filter ||
      typeof filter !== 'object' ||
      !('expression' in filter) ||
      typeof filter.expression !== 'string' ||
      filter.expression.trim() !== 'input.'
    )
      return []
    return [
      {
        severity: 'error',
        category: 'schema_violation',
        message: 'CEL filter: Syntax error at line 1, column 7.',
        node_id: 'id' in trigger && typeof trigger.id === 'string' ? trigger.id : null,
        field_path: 'parameters.filter.expression',
      },
    ]
  })
}

export function workflowFilterValidation(definition: unknown) {
  const findings = workflowFilterFindings(definition)
  return { is_valid: findings.length === 0, error_count: findings.length, warning_count: 0, findings }
}

export function workflowFilterProblem(definition: unknown) {
  const validation = workflowFilterValidation(definition)
  if (validation.is_valid) return
  return {
    type: 'https://api.example.com/errors/validation-error',
    title: 'Workflow Definition Invalid',
    detail: 'The workflow definition failed validation',
    code: 'WORKFLOW_DEFINITION_INVALID',
    retryable: false,
    validation_result: validation,
  }
}
