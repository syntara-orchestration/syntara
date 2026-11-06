import { ActivityTypeEnum, getNodeOutputSchema, type OutputFieldDef } from '@syntara/contracts'

import type { ChildWorkflowStepSchema } from '../hooks/useChildWorkflowSchema'
import type { InputSchemaPreviewNode } from '../views/InputSchemaPreview'

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
