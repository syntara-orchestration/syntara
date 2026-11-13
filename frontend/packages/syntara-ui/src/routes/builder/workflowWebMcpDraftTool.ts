import type { BuilderAction } from './builderReducer'
import { buildWorkflowDraft } from './workflowWebMcp'
import { DRAFT_SCHEMA } from './workflowWebMcpSchema'
import { getWorkflowSnapshot } from './workflowWebMcpState'
import type { ToolDefinition } from './workflowWebMcpToolTypes'

type WorkflowDraftToolActions = {
  canEdit: boolean
  isNew: boolean
  workflowName: string
  workflowDescription: string
  dispatch: (action: BuilderAction) => void
}

export function createWorkflowDraftTool(actionsRef: { current: WorkflowDraftToolActions }): ToolDefinition {
  return {
    name: 'create_workflow_draft',
    description:
      'On an empty new workflow builder, create a workflow draft with any user-selectable builder trigger and node type. Use nodes plus edges for scripts, HTTP requests, agents, AAP, approvals, conditions, switches, loops, waits, and converges. The legacy steps shortcut creates a simple chain. This edits the canvas only; it does not save or run the workflow.',
    inputSchema: DRAFT_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      const actions = actionsRef.current
      if (!actions.canEdit) return { ok: false, message: 'You do not have permission to edit this workflow.' }
      if (!actions.isNew) {
        return { ok: false, message: 'Open a new, empty workflow builder to create a draft with this tool.' }
      }

      const { store, currentWorkflow, edges } = getWorkflowSnapshot()
      const result = buildWorkflowDraft(input, currentWorkflow, edges)
      if (!result.ok) return result

      store.replaceWorkflowContent(result.workflow, result.edges)
      actionsRef.current = {
        ...actions,
        workflowName: result.name,
        workflowDescription: result.description,
      }
      actions.dispatch({ type: 'SET_WORKFLOW_NAME', payload: result.name })
      actions.dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: result.description })

      return {
        ok: true,
        saved: false,
        run_started: false,
        name: result.name,
        description: result.description,
        trigger_count: result.workflow.triggers?.length ?? 0,
        triggers: result.workflow.triggers?.map((trigger, index) => ({
          index,
          type: trigger.type,
          name: trigger.name,
        })),
        steps: result.workflow.workflow.activities.map((activity) => ({
          id: activity.id,
          type: activity.type,
          name: activity.name,
        })),
        connections: result.edges.map((edge) => ({
          source: edge.source,
          source_handle: edge.sourceHandle,
          target: edge.target,
          target_handle: edge.targetHandle,
        })),
        message: 'Draft graph added to the canvas. Review node configuration and connections, validate, then save it.',
      }
    },
  }
}
