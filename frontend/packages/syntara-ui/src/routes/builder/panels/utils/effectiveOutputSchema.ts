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

function cloneFields(fields: OutputFieldDef[] | null): PreviewFieldDef[] | null {
  return fields?.map((field) => ({ ...field })) ?? null
}

/**
 * Resolve the fields shown before execution. Form nodes enrich their static
 * output with fields from the current stored form definition; other nodes keep
 * their generated schema and manual triggers retain their input-schema fallback.
 */
export function getEffectiveOutputSchema(
  node: ConfiguredOutputNode,
  triggers?: { id: string; parameters?: Record<string, unknown> }[]
): PreviewFieldDef[] | null {
  const staticFields = cloneFields(getNodeOutputSchema(node.type))
  const isFormNode = node.type === ActivityTypeEnum.FORM_PROMPT || node.type === TriggerTypeEnum.FORM_TRIGGER

  if (isFormNode) {
    const responseFields = formResponseFields(node.parameters?.form_definition)
    if (!responseFields || !staticFields) return staticFields

    return staticFields.map((field) =>
      field.name === 'response_data' ? { ...field, children: responseFields } : field
    )
  }

  if (staticFields) return staticFields
  return getTriggerInputSchemaFields(node.id, triggers)
}
