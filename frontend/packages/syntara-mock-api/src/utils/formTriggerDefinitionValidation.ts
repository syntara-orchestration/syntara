/**
 * Lightweight form_trigger form_definition checks for mock workflow save responses.
 * Mirrors save-time validation findings (warnings) without running the full backend validator.
 */

export type MockValidationFinding = {
  severity: 'warning' | 'error'
  category: 'form_trigger_configuration'
  message: string
  node_id: string | null
  field_path: string | null
}

const VALUE_NAME_PATTERN = /^[a-z][a-z0-9_]*$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function formTriggerFindingsForParameters(
  triggerId: string,
  parameters: Record<string, unknown>
): MockValidationFinding[] {
  const findings: MockValidationFinding[] = []
  const formDefinition = parameters.form_definition
  if (!isRecord(formDefinition) || !Array.isArray(formDefinition.fields)) {
    findings.push({
      severity: 'warning',
      category: 'form_trigger_configuration',
      message: 'Form trigger form definition is missing or invalid',
      node_id: triggerId,
      field_path: 'parameters.form_definition',
    })
    return findings
  }

  const seenValueNames = new Map<string, number>()
  for (const [index, rawField] of formDefinition.fields.entries()) {
    if (!isRecord(rawField)) {
      continue
    }
    const valueName = rawField.value_name
    if (typeof valueName !== 'string') {
      findings.push({
        severity: 'warning',
        category: 'form_trigger_configuration',
        message: 'Form field value name is required',
        node_id: triggerId,
        field_path: `parameters.form_definition.fields.${index}.value_name`,
      })
      continue
    }
    if (!VALUE_NAME_PATTERN.test(valueName)) {
      findings.push({
        severity: 'warning',
        category: 'form_trigger_configuration',
        message: `Form field value name "${valueName}" is invalid`,
        node_id: triggerId,
        field_path: `parameters.form_definition.fields.${index}.value_name`,
      })
    }
    if (seenValueNames.has(valueName)) {
      findings.push({
        severity: 'warning',
        category: 'form_trigger_configuration',
        message: `Duplicate form field value name "${valueName}"`,
        node_id: triggerId,
        field_path: `parameters.form_definition.fields.${index}.value_name`,
      })
    } else {
      seenValueNames.set(valueName, index)
    }
  }

  return findings
}

export function collectFormTriggerDefinitionFindings(
  workflowDefinition: unknown
): MockValidationFinding[] {
  if (!isRecord(workflowDefinition)) {
    return []
  }
  const triggers = workflowDefinition.triggers
  if (!Array.isArray(triggers)) {
    return []
  }

  const findings: MockValidationFinding[] = []
  for (const rawTrigger of triggers) {
    if (!isRecord(rawTrigger) || rawTrigger.type !== 'form_trigger') {
      continue
    }
    const triggerId = typeof rawTrigger.id === 'string' ? rawTrigger.id : null
    const parameters = isRecord(rawTrigger.parameters) ? rawTrigger.parameters : {}
    findings.push(...formTriggerFindingsForParameters(triggerId ?? 'form_trigger', parameters))
  }
  return findings
}

export function buildValidationResultFromFindings(findings: MockValidationFinding[]) {
  const warningCount = findings.filter((finding) => finding.severity === 'warning').length
  const errorCount = findings.filter((finding) => finding.severity === 'error').length
  return {
    is_valid: findings.length === 0,
    error_count: errorCount,
    warning_count: warningCount,
    findings,
  }
}
