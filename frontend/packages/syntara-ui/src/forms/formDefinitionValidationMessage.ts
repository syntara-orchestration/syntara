/** Parsed location for a form-definition validation issue (0-based indices). */
export type FormDefinitionErrorLocation = Readonly<{
  fieldIndex: number
  optionIndex?: number
  propertyKey?: string
}>

const PARAMETERS_FORM_PREFIX = 'parameters.form_definition.'
const FIELDS_BRACKET = /^fields\[(\d+)\](?:\.(.+))?$/
const FIELDS_DOT = /^fields\.(\d+)(?:\.(.+))?$/
const OPTION_VALUE_DOT = /^options\.values\.(\d+)(?:\.(.+))?$/
const OPTION_VALUE_BRACKET = /^options\.values\[(\d+)\](?:\.(.+))?$/

function parseSubPath(subPath: string | undefined): Pick<FormDefinitionErrorLocation, 'optionIndex' | 'propertyKey'> {
  if (!subPath) {
    return {}
  }

  const optionDot = OPTION_VALUE_DOT.exec(subPath)
  if (optionDot) {
    const optionIndex = Number(optionDot[1])
    return {
      optionIndex: Number.isNaN(optionIndex) ? undefined : optionIndex,
      propertyKey: optionDot[2]?.split('.').at(-1),
    }
  }

  const optionBracket = OPTION_VALUE_BRACKET.exec(subPath)
  if (optionBracket) {
    const optionIndex = Number(optionBracket[1])
    return {
      optionIndex: Number.isNaN(optionIndex) ? undefined : optionIndex,
      propertyKey: optionBracket[2]?.split('.').at(-1),
    }
  }

  return { propertyKey: subPath.split('.').at(-1) }
}

function parseFieldsSegment(relative: string): FormDefinitionErrorLocation | null {
  const bracketMatch = FIELDS_BRACKET.exec(relative)
  if (bracketMatch) {
    const fieldIndex = Number(bracketMatch[1])
    if (Number.isNaN(fieldIndex)) return null
    return { fieldIndex, ...parseSubPath(bracketMatch[2]) }
  }

  const dotMatch = FIELDS_DOT.exec(relative)
  if (dotMatch) {
    const fieldIndex = Number(dotMatch[1])
    if (Number.isNaN(fieldIndex)) return null
    return { fieldIndex, ...parseSubPath(dotMatch[2]) }
  }

  return null
}

/** Parse backend or zod-style paths that identify a row in the form field builder. */
export function parseFormDefinitionErrorLocation(path: string | null | undefined): FormDefinitionErrorLocation | null {
  if (!path) return null

  if (path.startsWith(PARAMETERS_FORM_PREFIX)) {
    return parseFieldsSegment(path.slice(PARAMETERS_FORM_PREFIX.length))
  }

  return parseFieldsSegment(path)
}

const VALUE_NAME_MESSAGE_PREFIX = 'String should match pattern'
const FIELD_LABEL_EMPTY =
  /^String must contain at least 1 character\(s\)$|^String should have at least 1 character$|^Too small: expected string to have >=1 character/

function propertyLabel(propertyKey: string | undefined): string | undefined {
  if (!propertyKey) return undefined
  if (propertyKey === 'value_name') return 'Value name'
  if (propertyKey === 'label') return 'Field label'
  if (propertyKey === 'display_label') return 'Option label'
  if (propertyKey === 'value') return 'Option value'
  return undefined
}

function humanizeRequiredMessage(namedProperty: string | undefined): string {
  if (namedProperty === 'Value name') return 'Value name is required'
  if (namedProperty === 'Field label') return 'Field label is required'
  if (namedProperty === 'Option label') return 'Option label is required'
  if (namedProperty === 'Option value') return 'Option value is required'
  return namedProperty ? `${namedProperty} is required` : 'This field is required'
}

function humanizeCoreMessage(raw: string, propertyKey?: string): string {
  const namedProperty = propertyLabel(propertyKey)

  if (raw.startsWith(VALUE_NAME_MESSAGE_PREFIX)) {
    return 'Value name must start with a letter or underscore, then use letters, numbers, or underscores only'
  }

  if (raw.includes('display_label') && raw.includes('empty')) {
    return 'Option label is required'
  }

  if (FIELD_LABEL_EMPTY.test(raw) || raw === "'' should be non-empty" || raw === '[] should be non-empty') {
    return humanizeRequiredMessage(namedProperty)
  }

  if (namedProperty === 'Value name' && (raw.includes('pattern') || raw.includes('match'))) {
    return 'Value name must start with a letter or underscore, then use letters, numbers, or underscores only'
  }

  return raw
}

function formatLocationPrefix(location: FormDefinitionErrorLocation): string {
  const fieldLabel = `Field ${location.fieldIndex + 1}`
  if (location.optionIndex !== undefined) {
    return `${fieldLabel} — Option ${location.optionIndex + 1}`
  }
  return fieldLabel
}

export type HumanizeFormDefinitionIssueMessageOptions = Readonly<{
  /** When false, omit "Field N" / "Option N" prefixes (messages beside the matching input). Default true. */
  includeFieldLocation?: boolean
}>

/**
 * Turn raw schema/API copy into builder-friendly messages.
 * Banner/list copy keeps field and option row context by default; inline builder inputs omit it.
 */
export function humanizeFormDefinitionIssueMessage(
  raw: string,
  path?: string | null,
  options?: HumanizeFormDefinitionIssueMessageOptions
): string {
  const location = parseFormDefinitionErrorLocation(path)
  const core = humanizeCoreMessage(raw, location?.propertyKey)
  const includeFieldLocation = options?.includeFieldLocation ?? true

  if (!location || !includeFieldLocation) {
    return core
  }

  return `${formatLocationPrefix(location)} — ${core}`
}
