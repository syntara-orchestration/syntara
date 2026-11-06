import { ActivityTypeEnum, getNodeOutputSchema, type OutputFieldDef } from '@syntara/contracts'

import type { ChildWorkflowStepSchema } from '../hooks/useChildWorkflowSchema'
import type { InputSchemaPreviewNode } from '../views/InputSchemaPreview'

const MAPPED_OUTPUT_SCHEMA_MARKER = 'x-syntara-output-mapped'

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

/** Convert the published node schema to picker fields, honoring mapped output names. */
export function getChildStepOutputFields(
  stepType: string,
  outputSchema: Record<string, unknown> | null
): OutputFieldDef[] | null {
  const knownFields = getNodeOutputSchema(stepType)
  if (!outputSchema) return null

  const properties = outputSchema['properties']
  if (!isRecord(properties)) return knownFields

  const knownFieldsByName = new Map((knownFields ?? []).map((field) => [field.name, field]))
  return Object.entries(properties).map(([name, value]) => {
    const property = isRecord(value) ? value : {}
    const knownField = knownFieldsByName.get(name)
    const isMappedOutput = property[MAPPED_OUTPUT_SCHEMA_MARKER] === true
    const type = isMappedOutput ? 'unknown' : (schemaFieldType(property) ?? knownField?.type ?? 'unknown')
    const description =
      typeof property['description'] === 'string' ? property['description'] : (knownField?.description ?? '')

    return {
      name,
      type,
      description,
      ...(!isMappedOutput && knownField?.children ? { children: knownField.children } : {}),
      ...(!isMappedOutput && knownField?.additionalProperties
        ? { additionalProperties: knownField.additionalProperties }
        : {}),
    }
  })
}

function toPreviewNode(field: OutputFieldDef, parentPath: string[]): InputSchemaPreviewNode {
  const fieldPath = [...parentPath, field.name]
  return {
    name: field.name,
    type: field.type,
    description: field.description,
    fieldPath,
    ...(field.children && field.children.length > 0
      ? { children: field.children.map((child) => toPreviewNode(child, fieldPath)), isGroup: true }
      : {}),
  }
}

function buildChildStepGroup(step: ChildWorkflowStepSchema, outputsPath: string[]): InputSchemaPreviewNode {
  const stepPath = [...outputsPath, step.id]
  const wrapperFields =
    getNodeOutputSchema(ActivityTypeEnum.SUB_WORKFLOW)
      ?.find((field) => field.name === 'Result')
      ?.children?.find((field) => field.name === 'outputs')?.additionalProperties ?? []

  const children = wrapperFields.map((wrapperField) => {
    const wrapperPath = [...stepPath, wrapperField.name]
    if (wrapperField.name === 'Result') {
      return {
        name: wrapperField.name,
        type: wrapperField.type,
        description: wrapperField.description,
        fieldPath: wrapperPath,
        isGroup: true,
        children: (step.outputFields ?? []).map((field) => toPreviewNode(field, wrapperPath)),
      }
    }
    return toPreviewNode(wrapperField, stepPath)
  })

  return {
    name: step.name,
    type: 'object',
    description: `Outputs from ${step.name}`,
    fieldPath: stepPath,
    isGroup: true,
    children,
  }
}

/** Build the Sub-workflow output tree from the published child-step schemas. */
export function buildSubWorkflowOutputSchemaTree(childSteps: ChildWorkflowStepSchema[]): InputSchemaPreviewNode[] {
  const outputFields = getNodeOutputSchema(ActivityTypeEnum.SUB_WORKFLOW) ?? []
  const childStepsWithFields = childSteps.filter((step) => (step.outputFields?.length ?? 0) > 0)

  const buildField = (field: OutputFieldDef, parentPath: string[]): InputSchemaPreviewNode => {
    const fieldPath = [...parentPath, field.name]
    if (fieldPath.length === 2 && fieldPath[0] === 'Result' && field.name === 'outputs') {
      if (childStepsWithFields.length === 0) {
        return { name: field.name, type: field.type, description: field.description, fieldPath }
      }
      return {
        name: field.name,
        type: field.type,
        description: field.description,
        fieldPath,
        isGroup: true,
        children: childStepsWithFields.map((step) => buildChildStepGroup(step, fieldPath)),
      }
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
