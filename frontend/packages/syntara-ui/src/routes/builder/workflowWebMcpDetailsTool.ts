import type { Dispatch } from 'react'

import type { BuilderAction } from './builderReducer'
import { cleanText, stripControlCharacters } from './workflowWebMcp'
import { getWorkflowSnapshot } from './workflowWebMcpState'
import type { ToolDefinition } from './workflowWebMcpToolTypes'

type WorkflowDetailsActions = {
  canEdit: boolean
  workflowName: string
  workflowDescription: string
  dispatch: Dispatch<BuilderAction>
}

const WORKFLOW_DETAILS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    name: { type: 'string', minLength: 1, maxLength: 255 },
    description: { type: 'string', maxLength: 1024 },
  },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function cleanDescription(value: unknown): string {
  if (typeof value !== 'string') throw new Error('Workflow description must be text.')
  const description = stripControlCharacters(value).trim()
  if (description.length > 1024) throw new Error('Workflow description must be 1024 characters or fewer.')
  return description
}

export function createWorkflowDetailsTool(actionsRef: { current: WorkflowDetailsActions }): ToolDefinition {
  return {
    name: 'update_workflow_details',
    description:
      'Update the open workflow name and/or description in the builder draft. This does not save the workflow; call save_workflow to persist the change.',
    inputSchema: WORKFLOW_DETAILS_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      const actions = actionsRef.current
      if (!actions.canEdit) return { ok: false, message: 'You do not have permission to edit this workflow.' }
      if (!getWorkflowSnapshot().currentWorkflow) {
        return { ok: false, message: 'The workflow builder is still loading.' }
      }
      if (!isRecord(input)) return { ok: false, message: 'Provide a name or description to update.' }
      const keys = Object.keys(input)
      if (keys.some((key) => key !== 'name' && key !== 'description')) {
        return { ok: false, message: 'Only workflow name and description can be updated by this tool.' }
      }
      if (!Object.hasOwn(input, 'name') && !Object.hasOwn(input, 'description')) {
        return { ok: false, message: 'Provide a name or description to update.' }
      }

      try {
        const name = Object.hasOwn(input, 'name') ? cleanText(input.name, 'Workflow name', 255) : actions.workflowName
        const description = Object.hasOwn(input, 'description')
          ? cleanDescription(input.description)
          : actions.workflowDescription
        const changedFields: string[] = []
        if (name !== actions.workflowName) {
          changedFields.push('name')
          actions.dispatch({ type: 'SET_WORKFLOW_NAME', payload: name })
        }
        if (description !== actions.workflowDescription) {
          changedFields.push('description')
          actions.dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: description })
        }
        actionsRef.current = { ...actions, workflowName: name, workflowDescription: description }
        return {
          ok: true,
          saved: false,
          changed_fields: changedFields,
          name,
          description,
          message:
            changedFields.length > 0
              ? 'Updated workflow details in the builder draft.'
              : 'Workflow details are unchanged.',
        }
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : 'Workflow details could not be updated.' }
      }
    },
  }
}
