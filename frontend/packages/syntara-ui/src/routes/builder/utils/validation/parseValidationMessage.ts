import { humanizeFormDefinitionIssueMessage } from '../../../../forms'
import { AUTHORIZED_SERVICE_ACCOUNT_REQUIRED_MESSAGE } from '../../step-forms/triggerFormSchema'

const KEY_PREFIX_PATTERN = /^(\w+(?:\.\w+)*): /

export type ParsedValidationMessage = {
  key: string
  displayKey: string
  messages: string[]
}

export function parseValidationMessage(raw: string): ParsedValidationMessage {
  const keyMatch = KEY_PREFIX_PATTERN.exec(raw)
  if (!keyMatch) {
    return { key: 'Workflow', displayKey: 'Workflow', messages: [raw] }
  }

  const key = keyMatch[1]
  const rest = raw.substring(keyMatch[0].length)
  return { key, displayKey: key, messages: [rest] }
}

const ID_PATTERN = /^'([^']+)' does not match '\^/
const REQUIRED_PROPERTY_PATTERN = /^'([^']+)' is a required property$/
const NON_EMPTY_PATTERN = /^(?:''|\[\]) (?:should be non-empty|is too short)$/
const HUMANIZED_MISSING_FIELD = /^Missing required field "([^"]+)"$/
const VALUE_NAME_MESSAGE_PREFIX = 'String should match pattern'

const EMPTY_FIELD_MESSAGES: Record<string, string> = {
  authorized_service_account_ids: AUTHORIZED_SERVICE_ACCOUNT_REQUIRED_MESSAGE,
}

function extractFieldName(fieldPath: string | null | undefined): string | null {
  if (!fieldPath) return null
  const segments = fieldPath.split('.')
  return segments.at(-1) || null
}

function humanizeNonEmptyMessage(fieldPath?: string | null): string {
  const fieldName = extractFieldName(fieldPath)
  if (fieldName === 'display_label') {
    return 'Option label is required'
  }
  if (fieldName === 'value_name') {
    return 'Value name is required'
  }
  if (fieldName === 'label') {
    return 'Field label is required'
  }
  if (fieldName) {
    return EMPTY_FIELD_MESSAGES[fieldName] ?? `"${fieldName}" must not be empty`
  }
  return 'This field must not be empty'
}

export function humanizeValidationMessage(raw: string, fieldPath?: string | null): string {
  if (
    fieldPath &&
    (fieldPath.includes('form_definition.fields') || fieldPath.startsWith('fields[') || fieldPath.startsWith('fields.'))
  ) {
    return humanizeFormDefinitionIssueMessage(raw, fieldPath)
  }

  const idMatch = ID_PATTERN.exec(raw)
  if (idMatch) {
    return `"${idMatch[1]}" is not a valid ID. Use letters, numbers, and underscores only (e.g., "my_node_1")`
  }

  const requiredMatch = REQUIRED_PROPERTY_PATTERN.exec(raw)
  if (requiredMatch) {
    return EMPTY_FIELD_MESSAGES[requiredMatch[1]] ?? `Missing required field "${requiredMatch[1]}"`
  }

  if (NON_EMPTY_PATTERN.test(raw)) {
    return humanizeNonEmptyMessage(fieldPath)
  }

  if (raw.startsWith(VALUE_NAME_MESSAGE_PREFIX)) {
    return 'Value name must start with a letter or underscore, then use letters, numbers, or underscores only'
  }

  if (raw.includes('display_label') && raw.includes('empty')) {
    return 'Option label is required'
  }

  return raw
}

function joinWithAnd(items: string[]): string {
  if (items.length <= 1) return items.join('')
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(', ')}, and ${items.at(-1)}`
}

export function mergeHumanizedMessages(messages: string[]): string[] {
  const missingFields: string[] = []
  const other: string[] = []

  for (const msg of messages) {
    const match = HUMANIZED_MISSING_FIELD.exec(msg)
    if (match) {
      missingFields.push(`"${match[1]}"`)
    } else {
      other.push(msg)
    }
  }

  const result: string[] = []
  if (missingFields.length === 1) {
    result.push(`Missing required field ${missingFields[0]}`)
  } else if (missingFields.length > 1) {
    result.push(`Missing required fields ${joinWithAnd(missingFields)}`)
  }
  result.push(...other)
  return result
}
