import { ActivityTypeEnum, getNodeOutputSchema, type OutputFieldDef } from '@syntara/contracts'

import type { ChildWorkflowStepSchema } from '../hooks/useChildWorkflowSchema'
import type { InputSchemaPreviewNode } from '../views/InputSchemaPreview'

/**
 * Backend schema marker for mapped outputs.
 * MUST match the marker key set by _effective_output_schema_for_node in
 * backend/src/syntara/workflows/services/workflow_service.py.
 * Mapped outputs have unknown types until execution because their values
 * come from template expressions.
 */
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

  // Extract required fields from JSON Schema's required array
  const requiredFields = new Set(
    Array.isArray(outputSchema['required'])
      ? outputSchema['required'].filter((name): name is string => typeof name === 'string')
      : []
  )

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
      required: requiredFields.has(name),
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
    ...('required' in field && typeof field.required === 'boolean' ? { required: field.required } : {}),
    ...(field.children && field.children.length > 0
      ? { children: field.children.map((child) => toPreviewNode(child, fieldPath)), isGroup: true }
      : {}),
  }
}

function buildChildStepGroup(step: ChildWorkflowStepSchema, outputsPath: string[]): InputSchemaPreviewNode {
  const stepPath = [...outputsPath, step.id]

  // Child step outputs are exposed as flat objects - no StandardOutputWrapper at this level
  const children = (step.outputFields ?? []).map((field) => toPreviewNode(field, stepPath))

  return {
    name: step.name,
    type: 'object',
    description: `Outputs from ${step.name}`,
    fieldPath: stepPath,
    isGroup: true,
    children,
  }
}

/** Build the Sub-workflow output tree from declared outputs or legacy terminal steps. */
export function buildSubWorkflowOutputSchemaTree(childSteps: ChildWorkflowStepSchema[]): InputSchemaPreviewNode[] {
  const outputFields = getNodeOutputSchema(ActivityTypeEnum.SUB_WORKFLOW) ?? []

  // Check if we have declared outputs (new contract) vs legacy terminal steps
  const hasDeclaredOutputs = childSteps.length === 1 && childSteps[0]?.id === '__declared_outputs__'
  const declaredStep = hasDeclaredOutputs ? childSteps[0] : null
  const childStepsWithFields = hasDeclaredOutputs
    ? []
    : childSteps.filter((step) => (step.outputFields?.length ?? 0) > 0)

  const buildField = (field: OutputFieldDef, parentPath: string[]): InputSchemaPreviewNode => {
    const fieldPath = [...parentPath, field.name]

    // When we reach Result.outputs, populate with declared outputs or legacy child steps
    if (fieldPath.length === 2 && fieldPath[0] === 'Result' && field.name === 'outputs') {
      if (declaredStep?.outputFields && declaredStep.outputFields.length > 0) {
        // Declared output contract: flatten declared fields directly under Result.outputs
        return {
          name: field.name,
          type: field.type,
          description: 'Declared outputs from child workflow',
          fieldPath,
          isGroup: true,
          children: declaredStep.outputFields.map((declaredField) => toPreviewNode(declaredField, fieldPath)),
        }
      }

      if (childStepsWithFields.length === 0) {
        // No outputs declared
        return { name: field.name, type: field.type, description: field.description, fieldPath }
      }

      // Legacy terminal steps: nest under step IDs
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
