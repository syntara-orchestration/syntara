import type { Activity } from '@syntara/contracts'
import { useEffect, useRef, type Dispatch } from 'react'

import { workflowFetchClient } from '../../client'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'

import type { BuilderAction } from './builderReducer'
import type { EdgeConnection } from './types/edge'
import { buildWorkflowDefinition } from './utils/workflowDefinitionBuilder'
import { buildWorkflowDraft, validateWorkflowDraft } from './workflowWebMcp'
import { getWorkflowGuide, WORKFLOW_GUIDE_SCHEMA, WORKFLOW_GUIDE_TOPICS } from './workflowWebMcpGuide'
import { DRAFT_SCHEMA } from './workflowWebMcpSchema'

type WorkflowWebMcpToolsProps = {
  isNew: boolean
  workflowId: string | null
  workflowName: string
  workflowDescription: string
  selectedProjectId: string | null
  canEdit: boolean
  canRun: boolean
  handleSaveWorkflow: () => Promise<boolean>
  dispatch: Dispatch<BuilderAction>
}

type ToolDefinition = {
  name: string
  description: string
  inputSchema: Record<string, unknown>
  annotations: {
    readOnlyHint: boolean
    untrustedContentHint: boolean
    consequentialHint: boolean
  }
  execute: (input: unknown) => unknown
}

type ModelContext = {
  registerTool: (tool: ToolDefinition, options?: { signal?: AbortSignal }) => void | Promise<void>
}

type CurrentActions = WorkflowWebMcpToolsProps

const EMPTY_SCHEMA = { type: 'object', properties: {}, additionalProperties: false }

const RUN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    trigger_index: {
      type: 'integer',
      minimum: 0,
      description: 'Trigger to run, by its zero-based position in the builder. Defaults to 0.',
    },
  },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function isModelContext(value: unknown): value is ModelContext {
  return !!value && typeof value === 'object' && 'registerTool' in value && typeof value.registerTool === 'function'
}

function getWorkflowSnapshot() {
  const store = useWorkflowStore.getState()
  const currentWorkflow = store.currentWorkflow
  const activities = currentWorkflow?.workflow.activities ?? []
  const triggers = currentWorkflow?.triggers ?? []
  return { store, currentWorkflow, activities, triggers, edges: store.edges, nodePositions: store.nodePositions }
}

function getValidationSummary(activities: Activity[], edges: EdgeConnection[], triggers: Activity[]) {
  return validateWorkflowDraft(activities, edges, triggers)
}

function createGetWorkflowGuideTool(): ToolDefinition {
  return {
    name: 'get_syntara_guide',
    description:
      'Read concise Syntara and workflow-builder documentation. Call when the user asks what Syntara does, how workflows work, or what configuration a step needs. Request one topic at a time to keep context focused.',
    inputSchema: WORKFLOW_GUIDE_SCHEMA,
    annotations: { readOnlyHint: true, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      const topic = isRecord(input) ? input.topic : undefined
      const guide = getWorkflowGuide(topic)
      return guide
        ? { ok: true, topic, ...guide }
        : { ok: false, message: 'Choose one supported guide topic.', available_topics: WORKFLOW_GUIDE_TOPICS }
    },
  }
}

async function validateCurrentWorkflow(actions: CurrentActions) {
  const { currentWorkflow, activities, triggers, edges, nodePositions } = getWorkflowSnapshot()
  const frontend = getValidationSummary(activities, edges, triggers)
  if (!currentWorkflow) {
    return {
      ...frontend,
      errors: [...frontend.errors, 'The workflow builder is still loading.'],
      readyToRun: false,
      backendValidated: false,
    }
  }

  let definition: ReturnType<typeof buildWorkflowDefinition>
  try {
    definition = buildWorkflowDefinition({
      workflowName: actions.workflowName,
      workflowDescription: actions.workflowDescription,
      activities,
      triggers,
      edges,
      nodePositions,
    })
  } catch (error) {
    return {
      ...frontend,
      errors: [...frontend.errors, getErrorMessage(error)],
      readyToRun: false,
      backendValidated: false,
    }
  }

  try {
    const { data, error, response } = await workflowFetchClient.POST('/workflows/validate', {
      body: { workflow_definition: definition },
    })
    if (!response.ok || !data) {
      return {
        ...frontend,
        errors: [...frontend.errors, `Backend validation could not complete: ${getErrorMessage(error)}`],
        readyToRun: false,
        backendValidated: false,
      }
    }

    const findings = data.findings ?? []
    const backendErrors = findings.filter((finding) => finding.severity === 'error').map((finding) => finding.message)
    const backendWarnings = findings
      .filter((finding) => finding.severity === 'warning')
      .map((finding) => finding.message)
    const errors = [...new Set([...frontend.errors, ...backendErrors])]
    if (!data.is_valid && backendErrors.length === 0) errors.push('Backend validation failed.')

    return {
      errors,
      warnings: [...new Set([...frontend.warnings, ...backendWarnings])],
      readyToRun: frontend.readyToRun && data.is_valid && errors.length === 0,
      backendValidated: true,
    }
  } catch (error) {
    return {
      ...frontend,
      errors: [...frontend.errors, `Backend validation could not complete: ${getErrorMessage(error)}`],
      readyToRun: false,
      backendValidated: false,
    }
  }
}

function createGetBuilderStateTool(actionsRef: { current: CurrentActions }): ToolDefinition {
  return {
    name: 'get_workflow_builder_state',
    description:
      'Read the open Syntara workflow builder: workflow title, selected project, trigger and step names/types, graph connections and branch handles, dirty state, and available actions. Does not reveal node parameters or credentials.',
    inputSchema: EMPTY_SCHEMA,
    annotations: { readOnlyHint: true, untrustedContentHint: true, consequentialHint: false },
    execute: () => {
      const actions = actionsRef.current
      const { currentWorkflow, activities, triggers, store } = getWorkflowSnapshot()
      return {
        workflow_id: actions.workflowId,
        name: actions.workflowName,
        description: actions.workflowDescription,
        selected_project_id: actions.selectedProjectId,
        is_new: actions.isNew,
        is_dirty: store.isDirty,
        permissions: { can_edit: actions.canEdit, can_run: actions.canRun },
        triggers: triggers.map((trigger, index) => ({
          index,
          id: trigger.id,
          type: trigger.type,
          name: trigger.name,
        })),
        steps: activities.map((activity) => ({ id: activity.id, type: activity.type, name: activity.name })),
        connections: store.edges.map((edge) => ({
          source: edge.source,
          source_handle: edge.sourceHandle ?? null,
          target: edge.target,
          target_handle: edge.targetHandle ?? null,
        })),
        ready: currentWorkflow !== null,
      }
    },
  }
}

function createValidateWorkflowTool(actionsRef: { current: CurrentActions }): ToolDefinition {
  return {
    name: 'validate_workflow_draft',
    description:
      'Run Syntara client-side and backend workflow-definition checks. Report errors, warnings, and whether the workflow is ready to run.',
    inputSchema: EMPTY_SCHEMA,
    annotations: { readOnlyHint: true, untrustedContentHint: true, consequentialHint: false },
    execute: async () => {
      const validation = await validateCurrentWorkflow(actionsRef.current)
      return {
        ok: validation.errors.length === 0,
        backend_validated: validation.backendValidated,
        ready_to_run: validation.readyToRun,
        errors: validation.errors,
        warnings: validation.warnings,
      }
    },
  }
}

function createWorkflowDraftTool(actionsRef: { current: CurrentActions }): ToolDefinition {
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

function createSaveWorkflowTool(actionsRef: { current: CurrentActions }): ToolDefinition {
  return {
    name: 'save_workflow',
    description:
      'Save the current workflow using Syntara’s normal save path. A new workflow must have a project selected. This does not run the workflow.',
    inputSchema: EMPTY_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: false, consequentialHint: true },
    execute: async () => {
      const actions = actionsRef.current
      if (!actions.canEdit) return { ok: false, message: 'You do not have permission to save this workflow.' }
      if (!getWorkflowSnapshot().currentWorkflow) {
        return { ok: false, message: 'The workflow builder is still loading.' }
      }
      if (actions.isNew && !actions.selectedProjectId) {
        return { ok: false, message: 'Select a project in the builder before saving this new workflow.' }
      }

      const saved = await actions.handleSaveWorkflow()
      return saved
        ? { ok: true, saved: true, message: 'Workflow saved.' }
        : {
            ok: false,
            saved: false,
            message: 'Save did not complete. Check the builder for validation or editor prompts.',
          }
    },
  }
}

function createRequestWorkflowRunTool(actionsRef: { current: CurrentActions }): ToolDefinition {
  return {
    name: 'request_workflow_run',
    description:
      'Check the saved workflow and open Syntara’s run confirmation dialog. A person must confirm the run and provide trigger input when needed; this tool never starts execution directly.',
    inputSchema: RUN_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: true, consequentialHint: true },
    execute: async (input) => {
      const actions = actionsRef.current
      if (!actions.canRun) return { ok: false, message: 'You do not have permission to run this workflow.' }
      if (!actions.workflowId || actions.isNew) {
        return { ok: false, message: 'Save the workflow first, then request a run.' }
      }

      const { triggers } = getWorkflowSnapshot()
      if (triggers.length === 0) return { ok: false, message: 'Add a trigger before requesting a run.' }

      const triggerIndex = isRecord(input) && input.trigger_index !== undefined ? input.trigger_index : 0
      if (
        typeof triggerIndex !== 'number' ||
        !Number.isInteger(triggerIndex) ||
        triggerIndex < 0 ||
        triggerIndex >= triggers.length
      ) {
        return { ok: false, message: `trigger_index must be between 0 and ${triggers.length - 1}.` }
      }

      const validation = await validateCurrentWorkflow(actions)
      if (!validation.readyToRun) {
        return {
          ok: false,
          backend_validated: validation.backendValidated,
          ready_to_run: false,
          errors: validation.errors,
          warnings: validation.warnings,
        }
      }

      actions.dispatch({ type: 'SET_SELECTED_TRIGGER', payload: triggerIndex })
      actions.dispatch({ type: 'SET_FORCE_RUN_CONFIRMATION', payload: true })
      actions.dispatch({ type: 'SET_CONFIRM_DIALOG', payload: true })

      return {
        ok: true,
        confirmation_required: true,
        run_started: false,
        trigger: triggers[triggerIndex]?.name ?? `Trigger ${triggerIndex + 1}`,
        message: 'Run confirmation is open in Syntara. Confirm there to start execution.',
      }
    },
  }
}

function buildToolDefinitions(actionsRef: { current: CurrentActions }): ToolDefinition[] {
  const actions = actionsRef.current
  const tools = [
    createGetWorkflowGuideTool(),
    createGetBuilderStateTool(actionsRef),
    createValidateWorkflowTool(actionsRef),
  ]
  if (actions.canEdit && actions.isNew) tools.push(createWorkflowDraftTool(actionsRef))
  if (actions.canEdit) tools.push(createSaveWorkflowTool(actionsRef))
  if (actions.canRun && actions.workflowId && !actions.isNew) {
    tools.push(createRequestWorkflowRunTool(actionsRef))
  }
  return tools
}

export function WorkflowWebMcpTools(props: WorkflowWebMcpToolsProps) {
  const {
    isNew,
    workflowId,
    workflowName,
    workflowDescription,
    selectedProjectId,
    canEdit,
    canRun,
    handleSaveWorkflow,
    dispatch,
  } = props
  const actionsRef = useRef<CurrentActions>(props)

  useEffect(() => {
    actionsRef.current = {
      isNew,
      workflowId,
      workflowName,
      workflowDescription,
      selectedProjectId,
      canEdit,
      canRun,
      handleSaveWorkflow,
      dispatch,
    }
  }, [
    isNew,
    workflowId,
    workflowName,
    workflowDescription,
    selectedProjectId,
    canEdit,
    canRun,
    handleSaveWorkflow,
    dispatch,
  ])

  useEffect(() => {
    if (typeof document === 'undefined') return
    const modelContextValue = 'modelContext' in document ? document.modelContext : undefined
    if (!isModelContext(modelContextValue)) return

    const tools = buildToolDefinitions(actionsRef)
    const controller = new AbortController()
    let active = true

    const registerTools = async () => {
      for (const tool of tools) {
        if (!active) return
        try {
          await modelContextValue.registerTool(tool, { signal: controller.signal })
        } catch {
          controller.abort()
          return
        }
      }
    }
    detachPromise(registerTools())

    return () => {
      active = false
      controller.abort()
    }
  }, [props.canEdit, props.canRun, props.isNew, props.workflowId])

  return null
}
