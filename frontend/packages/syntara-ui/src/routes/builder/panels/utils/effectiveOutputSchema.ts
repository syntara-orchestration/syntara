import {
  ActivityTypeEnum,
  FormFieldTypeEnum,
  TriggerTypeEnum,
  getNodeOutputSchema,
  type FormField,
  type OutputFieldDef,
} from '@syntara/contracts'

import { safeParseFormDefinition } from '../../../../forms/formDefinitionSchema'
import { formDefinitionToJsonSchema } from '../../../../forms/formDefinitionToJsonSchema'

import { mapJsonSchemaPropertyType } from './jsonSchemaPreviewUtils'
import { getTriggerInputSchemaFields } from './triggerSchemaUtils'

/** Output fields used by the input preview, including configuration-derived children. */
export type PreviewFieldDef = OutputFieldDef & {
  displayName?: string
  children?: PreviewFieldDef[]
}

export type ConfiguredOutputNode = {
  id: string
  type: string
  parameters?: Record<string, unknown>
}

type JsonSchemaProperty = Record<string, unknown>

function outputTypeFromSchema(schemaType: unknown): OutputFieldDef['type'] {
  if (typeof schemaType !== 'string') return 'unknown'

  switch (schemaType) {
    case 'string':
    case 'number':
    case 'boolean':
    case 'object':
    case 'array':
      return schemaType
    default:
      return 'unknown'
  }
}

function resolvedOptionOutputType(
  field: Extract<FormField, { type: typeof FormFieldTypeEnum.DROPDOWN }>
): OutputFieldDef['type'] {
  if (field.options.source !== 'dynamic_resolved') {
    return 'unknown'
  }

  const firstOption = field.options.values[0]
  if (!firstOption) return 'unknown'

  const firstType = typeof firstOption.value
  if (field.options.values.some((option) => typeof option.value !== firstType)) {
    return 'unknown'
  }

  return outputTypeFromSchema(firstType)
}

function formFieldOutputType(field: FormField, property: JsonSchemaProperty | undefined): OutputFieldDef['type'] {
  switch (field.type) {
    case FormFieldTypeEnum.DATE:
      // The backend returns one string for every collected date/time combination.
      return 'string'
    case FormFieldTypeEnum.MULTI_SELECT:
      return 'array'
    case FormFieldTypeEnum.DROPDOWN:
      if (field.options.source === 'dynamic') return 'unknown'
      if (field.options.source === 'dynamic_resolved') return resolvedOptionOutputType(field)
      return outputTypeFromSchema(property?.type)
    case FormFieldTypeEnum.TEXT:
    case FormFieldTypeEnum.EMAIL:
    case FormFieldTypeEnum.NUMBER:
    case FormFieldTypeEnum.CHECKBOX:
      return outputTypeFromSchema(property?.type)
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const BLANK_DYNAMIC_OPTION_PLACEHOLDER = '_'

function fillBlankDynamicOptionKeys(options: Record<string, unknown>): Record<string, unknown> {
  const filled = { ...options }
  for (const key of ['expression', 'label_key', 'value_key']) {
    const value = filled[key]
    if (typeof value !== 'string' || value.trim() === '') {
      filled[key] = BLANK_DYNAMIC_OPTION_PLACEHOLDER
    }
  }
  return filled
}

/**
 * The field builder seeds blank dynamic option settings while the user is still
 * configuring a field. Those settings do not affect which fields a form returns,
 * so they must not invalidate the whole definition for the output preview.
 */
function tolerateUnfinishedDynamicOptions(formDefinition: unknown): unknown {
  if (!isRecord(formDefinition) || !Array.isArray(formDefinition.fields)) return formDefinition

  const fields: unknown[] = formDefinition.fields.map((field: unknown) => {
    if (!isRecord(field) || !isRecord(field.options) || field.options.source !== 'dynamic') return field
    return { ...field, options: fillBlankDynamicOptionKeys(field.options) }
  })
  return { ...formDefinition, fields }
}

function formResponseFields(formDefinition: unknown): PreviewFieldDef[] | null {
  const parsed = safeParseFormDefinition(tolerateUnfinishedDynamicOptions(formDefinition))
  // An empty field list has nothing to preview; don't rely on the schema's minimum-field rule alone.
  if (!parsed.success || parsed.data.fields.length === 0) return null

  const jsonSchema = formDefinitionToJsonSchema(parsed.data)
  return parsed.data.fields.map((field) => ({
    name: field.value_name,
    type: formFieldOutputType(field, jsonSchema.properties[field.value_name]),
    description: field.help_text ?? '',
    displayName: field.label,
  }))
}

function previewFieldsFromJsonSchema(responseSchema: unknown): PreviewFieldDef[] | null {
  if (!isRecord(responseSchema)) return null

  const properties = responseSchema.properties
  if (!isRecord(properties) || Object.keys(properties).length === 0) return null

  return Object.entries(properties).map(([name, propertyValue]) => {
    const property = isRecord(propertyValue) ? propertyValue : {}
    const description = typeof property.description === 'string' ? property.description : ''

    return {
      name,
      type: mapJsonSchemaPropertyType(property),
      description,
      displayName: name,
    }
  })
}

function sortedFieldNames(names: string[]): string {
  return [...names].sort((left, right) => left.localeCompare(right)).join('\0')
}

function formDefinitionFieldNames(formDefinition: unknown): string[] | null {
  const parsed = safeParseFormDefinition(tolerateUnfinishedDynamicOptions(formDefinition))
  if (!parsed.success) return null
  return parsed.data.fields.map((field) => field.value_name)
}

function previewTypesAlign(derived: PreviewFieldDef, persisted: PreviewFieldDef): boolean {
  if (derived.type === 'unknown' || persisted.type === 'unknown') return true
  return derived.type === persisted.type
}

function persistedResponseSchemaMatchesFormDefinition(
  formDefinition: unknown,
  derivedFields: PreviewFieldDef[] | null,
  persistedFields: PreviewFieldDef[] | null
): boolean {
  const formFieldNames = formDefinitionFieldNames(formDefinition)
  if (formFieldNames === null) return false

  if (!persistedFields) return formFieldNames.length === 0

  if (sortedFieldNames(formFieldNames) !== sortedFieldNames(persistedFields.map((field) => field.name))) {
    return false
  }

  if (!derivedFields) return true

  const persistedByName = new Map(persistedFields.map((field) => [field.name, field]))
  return derivedFields.every((derived) => {
    const persisted = persistedByName.get(derived.name)
    return persisted !== undefined && previewTypesAlign(derived, persisted)
  })
}

function enrichPersistedFieldsWithDerivedLabels(
  persistedFields: PreviewFieldDef[],
  derivedFields: PreviewFieldDef[]
): PreviewFieldDef[] {
  const persistedByName = new Map(persistedFields.map((field) => [field.name, field]))

  return derivedFields.flatMap((derived) => {
    const field = persistedByName.get(derived.name)
    if (!field) return []

    return [
      {
        ...field,
        displayName: derived.displayName,
        description: derived.description || field.description,
      },
    ]
  })
}

function resolveFormResponseDataFields(parameters: Record<string, unknown> | undefined): PreviewFieldDef[] | null {
  const derivedFields = formResponseFields(parameters?.form_definition)
  const persistedFields = previewFieldsFromJsonSchema(parameters?.response_schema)

  if (
    derivedFields &&
    persistedFields &&
    persistedResponseSchemaMatchesFormDefinition(parameters?.form_definition, derivedFields, persistedFields)
  ) {
    return enrichPersistedFieldsWithDerivedLabels(persistedFields, derivedFields)
  }

  if (derivedFields) return derivedFields
  return persistedFields
}

function cloneFields(fields: OutputFieldDef[] | null): PreviewFieldDef[] | null {
  return fields?.map((field) => ({ ...field })) ?? null
}

/**
 * Resolve the fields shown before execution. Form nodes enrich their static
 * output with `response_data` children from the persisted `response_schema` when
 * it matches the current `form_definition` (names and preview types), otherwise
 * from local derivation, with a legacy fallback to `response_schema` alone.
 * Other nodes keep their generated schema; manual triggers retain their input-schema fallback.
 */
export function getEffectiveOutputSchema(
  node: ConfiguredOutputNode,
  triggers?: { id: string; parameters?: Record<string, unknown> }[]
): PreviewFieldDef[] | null {
  const staticFields = cloneFields(getNodeOutputSchema(node.type))
  const isFormNode = node.type === ActivityTypeEnum.FORM_PROMPT || node.type === TriggerTypeEnum.FORM_TRIGGER

  if (isFormNode) {
    const responseFields = resolveFormResponseDataFields(node.parameters)
    if (!responseFields || !staticFields) return staticFields

    return staticFields.map((field) =>
      field.name === 'response_data' ? { ...field, children: responseFields } : field
    )
  }

  if (staticFields) return staticFields
  return getTriggerInputSchemaFields(node.id, triggers)
}
