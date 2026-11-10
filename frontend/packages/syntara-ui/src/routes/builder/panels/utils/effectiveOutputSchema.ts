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
    case FormFieldTypeEnum.TEXTAREA:
    case FormFieldTypeEnum.MASKED_TEXT:
    case FormFieldTypeEnum.EMAIL:
    case FormFieldTypeEnum.NUMBER:
    case FormFieldTypeEnum.CHECKBOX:
      return outputTypeFromSchema(property?.type)
  }
}

function formResponseFields(formDefinition: unknown): PreviewFieldDef[] | null {
  const parsed = safeParseFormDefinition(formDefinition)
  if (!parsed.success) return null

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
