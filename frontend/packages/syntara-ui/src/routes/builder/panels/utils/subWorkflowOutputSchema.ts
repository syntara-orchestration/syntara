import { ActivityTypeEnum, getNodeOutputSchema, type OutputFieldDef } from '@syntara/contracts'

import type { ChildWorkflowStepSchema } from '../hooks/useChildWorkflowSchema'
import type { InputSchemaPreviewNode } from '../views/InputSchemaPreview'

type OutputSchemaField = OutputFieldDef & { required?: boolean }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function schemaFieldType(schema: Record<string, unknown>): OutputFieldDef['type'] | null {
  const schemaType = Array.isArray(schema['type'])
    ? schema['type'].find((type): type is string => typeof type === 'string' && type !== 'null')
    : schema['type']

  switch (schemaType) {
    case 'string':
      return 'string'
    case 'integer':
    case 'number':
      return 'number'
    case 'boolean':
      return 'boolean'
    case 'object':
      return 'object'
    case 'array':
      return 'array'
    default:
      if (isRecord(schema['properties']) || schema['additionalProperties'] !== undefined) return 'object'
      if (schema['items'] !== undefined) return 'array'
      return null
  }
}

function outputFieldsFromProperties(
  properties: Record<string, unknown>,
  requiredProperties: Set<string>
): OutputSchemaField[] {
  return Object.entries(properties).flatMap(([name, value]) => {
    if (!isRecord(value)) return []
    const nestedProperties = value['properties']
    const nestedRequired = Array.isArray(value['required'])
      ? value['required'].filter((field): field is string => typeof field === 'string')
      : []
    const children = isRecord(nestedProperties)
      ? outputFieldsFromProperties(nestedProperties, new Set(nestedRequired))
      : undefined
    const type = schemaFieldType(value) ?? 'unknown'
    const field: OutputSchemaField = {
      name,
      type,
      description: typeof value['description'] === 'string' ? value['description'] : '',
      required: requiredProperties.has(name),
      ...(children && children.length > 0 ? { children } : {}),
    }
    return [field]
  })
}

/** Convert the selected trigger's declared output schema to picker fields. */
export function getDeclaredOutputFields(outputSchema: Record<string, unknown> | null): OutputSchemaField[] | null {
  if (!outputSchema) return null

  const properties = outputSchema['properties']
  if (!isRecord(properties)) return null

  const requiredFields = new Set(
    Array.isArray(outputSchema['required'])
      ? outputSchema['required'].filter((name): name is string => typeof name === 'string')
      : []
  )

  return outputFieldsFromProperties(properties, requiredFields)
}

function toPreviewNode(field: OutputFieldDef, parentPath: string[]): InputSchemaPreviewNode {
  const fieldPath = [...parentPath, field.name]
  return {
    name: field.name,
    type: field.type,
    description: field.description,
    fieldPath,
    ...('required' in field && typeof field.required === 'boolean' ? { required: field.required } : {}),
    ...(field.children && field.children.length > 0
      ? { children: field.children.map((child) => toPreviewNode(child, fieldPath)), isGroup: true }
      : {}),
  }
}

/** Build the Sub-workflow output tree from the selected trigger's declared outputs. */
export function buildSubWorkflowOutputSchemaTree(childSteps: ChildWorkflowStepSchema[]): InputSchemaPreviewNode[] {
  const outputFields = getNodeOutputSchema(ActivityTypeEnum.SUB_WORKFLOW) ?? []
  const declaredStep = childSteps.find((step) => step.id === '__declared_outputs__')

  const buildField = (field: OutputFieldDef, parentPath: string[]): InputSchemaPreviewNode => {
    const fieldPath = [...parentPath, field.name]

    // Populate the top-level outputs field with the selected trigger's public fields.
    if (parentPath.length === 0 && field.name === 'outputs') {
      if (declaredStep?.outputFields && declaredStep.outputFields.length > 0) {
        // Declared output contract: flatten declared fields directly under outputs.
        return {
          name: field.name,
          type: field.type,
          description: 'Declared outputs from child workflow',
          fieldPath,
          isGroup: true,
          children: declaredStep.outputFields.map((declaredField) => toPreviewNode(declaredField, fieldPath)),
        }
      }

      return { name: field.name, type: field.type, description: field.description, fieldPath }
    }

    return {
      name: field.name,
      type: field.type,
      description: field.description,
      fieldPath,
      ...(field.children && field.children.length > 0
        ? { children: field.children.map((child) => buildField(child, fieldPath)), isGroup: true }
        : {}),
    }
  }

  return outputFields.map((field) => buildField(field, []))
}
