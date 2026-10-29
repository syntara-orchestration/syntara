import type { Activity } from '@syntara/contracts'
import { useReactFlow } from '@xyflow/react'
import { useCallback, useEffect, useRef, type Dispatch } from 'react'

import { workflowFetchClient } from '../../client'
import { useProjectStore } from '../../stores/useProjectStore'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { buildTriggerNodeId } from '../../utils/triggerNodeIds'
import type { ProjectRead } from '../access/types'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import type { BuilderAction } from './builderReducer'
import type { EdgeConnection } from './types/edge'
import { buildWorkflowDefinition } from './utils/workflowDefinitionBuilder'
import type { EdgeType } from './utils/workflowToGraph'
import { validateWorkflowDraft } from './workflowWebMcp'
import { createWorkflowConnectionTools, saveCanvasConnection } from './workflowWebMcpConnectionTools'
import { createWorkflowDetailsTool } from './workflowWebMcpDetailsTool'
import { createWorkflowDraftTool } from './workflowWebMcpDraftTool'
import { getWorkflowGuide, WORKFLOW_GUIDE_SCHEMA, WORKFLOW_GUIDE_TOPICS } from './workflowWebMcpGuide'
import { createWorkflowNodeTools, getAvailableSourceHandles } from './workflowWebMcpNodeTools'
import { getWorkflowSnapshot } from './workflowWebMcpState'
import type { CanvasConnectionInput, ToolDefinition, WorkflowCanvasActions } from './workflowWebMcpToolTypes'

type WorkflowWebMcpToolsProps = {
  isNew: boolean
  workflowId: string | null
  workflowName: string
  workflowDescription: string
  selectableProjects: ProjectRead[]
  selectableProjectsLoading: boolean
  selectableProjectsFailed: boolean
  selectProject: (project: ProjectRead) => boolean
  canEdit: boolean
  canRun: boolean
  handleSaveWorkflow: () => Promise<boolean>
  dispatch: Dispatch<BuilderAction>
}

type ModelContext = {
  registerTool: (tool: ToolDefinition, options?: { signal?: AbortSignal }) => void | Promise<void>
}

type CurrentActions = WorkflowWebMcpToolsProps & WorkflowCanvasActions

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

type ProjectSelectionResolution =
  | { ok: true; project: ProjectRead }
  | { ok: false; message: string; matching_projects?: { id: string | undefined; name: string }[] }

function resolveProjectSelection(input: unknown, projects: ProjectRead[]): ProjectSelectionResolution {
  if (!isRecord(input)) return { ok: false, message: 'Provide project_name or project_id.' }

  const projectName = typeof input.project_name === 'string' ? input.project_name.trim() : ''
  const projectId = typeof input.project_id === 'string' ? input.project_id.trim() : ''
  if (Boolean(projectName) === Boolean(projectId)) {
    return { ok: false, message: 'Provide exactly one of project_name or project_id.' }
  }

  const normalizedName = projectName.toLowerCase()
  const matches = projects.filter((project) =>
    projectId ? project.id === projectId : project.name.trim().toLowerCase() === normalizedName
  )
  if (matches.length === 1) {
    const [project] = matches
    if (project) return { ok: true, project }
  }

  const suggestions = projectName
    ? projects
        .filter((project) => project.name.toLowerCase().includes(normalizedName))
        .slice(0, 5)
        .map((project) => ({ id: project.id, name: project.name }))
    : []
  return {
    ok: false,
    message:
      matches.length > 1
        ? 'More than one selectable project matched. Select by project_id.'
        : 'No selectable project matched the requested name or ID.',
    ...(suggestions.length > 0 ? { matching_projects: suggestions } : {}),
  }
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
      const selectedProject = useProjectStore.getState()
      return {
        workflow_id: actions.workflowId,
        name: actions.workflowName,
        description: actions.workflowDescription,
        selected_project_id: selectedProject.selectedProjectId,
        selected_project_name: selectedProject.selectedProjectName,
        is_new: actions.isNew,
        is_dirty: store.isDirty,
        permissions: { can_edit: actions.canEdit, can_run: actions.canRun },
        triggers: triggers.map((trigger, index) => ({
          index,
          id: trigger.id,
          canvas_node_id: buildTriggerNodeId(index),
          type: trigger.type,
          name: trigger.name,
          source_handles: getAvailableSourceHandles(trigger, true),
        })),
        steps: activities.map((activity) => ({
          id: activity.id,
          type: activity.type,
          name: activity.name,
          source_handles: getAvailableSourceHandles(activity),
        })),
        connections: store.edges.map((edge) => ({
          id: edge.id,
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

function createSelectWorkflowProjectTool(actionsRef: { current: CurrentActions }): ToolDefinition {
  return {
    name: 'select_workflow_project',
    description:
      'Select a non-built-in project for this new workflow. Provide exactly one of project_name (exact name, case-insensitive) or project_id. Use before saving; this changes the builder selection only and does not save the workflow.',
    inputSchema: {
      type: 'object',
      additionalProperties: false,
      properties: {
        project_name: {
          type: 'string',
          minLength: 1,
          description: 'Exact project name to select, matched without case sensitivity.',
        },
        project_id: { type: 'string', minLength: 1, description: 'ID of a selectable non-built-in project.' },
      },
    },
    annotations: { readOnlyHint: false, untrustedContentHint: false, consequentialHint: false },
    execute: (input) => {
      const actions = actionsRef.current
      if (!actions.canEdit) return { ok: false, message: 'You do not have permission to edit this workflow.' }
      if (!actions.isNew) {
        return { ok: false, message: 'Project selection is available only for a new workflow.' }
      }
      if (actions.selectableProjectsLoading) {
        return { ok: false, message: 'The selectable project list is still loading. Try again shortly.' }
      }
      if (actions.selectableProjectsFailed) {
        return {
          ok: false,
          message: 'The selectable project list could not be loaded. Check the builder and try again.',
        }
      }

      const resolution = resolveProjectSelection(input, actions.selectableProjects)
      if (!resolution.ok) return resolution
      if (!actions.selectProject(resolution.project)) {
        return { ok: false, message: 'The selected project could not be applied in the builder.' }
      }
      return {
        ok: true,
        selected_project: { id: resolution.project.id, name: resolution.project.name },
        message: `Selected project ${resolution.project.name}.`,
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
      if (actions.isNew && !useProjectStore.getState().selectedProjectId) {
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
    ...createWorkflowNodeTools(actionsRef),
    ...createWorkflowConnectionTools(actionsRef),
    createValidateWorkflowTool(actionsRef),
  ]
  if (actions.canEdit && actions.isNew) tools.push(createSelectWorkflowProjectTool(actionsRef))
  if (actions.canEdit && actions.isNew) tools.push(createWorkflowDraftTool(actionsRef))
  if (actions.canEdit) tools.push(createWorkflowDetailsTool(actionsRef))
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
    selectableProjects,
    selectableProjectsLoading,
    selectableProjectsFailed,
    selectProject,
    canEdit,
    canRun,
    handleSaveWorkflow,
    dispatch,
  } = props
  const reactFlowInstance = useReactFlow<NodeType, EdgeType>()
  const deleteCanvasNode = useCallback(
    async (nodeId: string) => {
      const previousIds = getWorkflowSnapshot().activities.map((activity) => activity.id)
      await reactFlowInstance.deleteElements({ nodes: [{ id: nodeId }] })
      const currentIds = new Set(getWorkflowSnapshot().activities.map((activity) => activity.id))
      return previousIds.filter((id) => !currentIds.has(id))
    },
    [reactFlowInstance]
  )
  const deleteCanvasConnection = useCallback(
    async (edgeId: string) => {
      const result = await reactFlowInstance.deleteElements({ edges: [{ id: edgeId }] })
      return result.deletedEdges.some((edge) => edge.id === edgeId)
    },
    [reactFlowInstance]
  )
  const saveCanvasConnectionAction = useCallback(
    (input: CanvasConnectionInput) => {
      return saveCanvasConnection(input, reactFlowInstance)
    },
    [reactFlowInstance]
  )
  const actionsRef = useRef<CurrentActions>({
    ...props,
    deleteCanvasNode,
    deleteCanvasConnection,
    saveCanvasConnection: saveCanvasConnectionAction,
  })

  useEffect(() => {
    actionsRef.current = {
      isNew,
      workflowId,
      workflowName,
      workflowDescription,
      selectableProjects,
      selectableProjectsLoading,
      selectableProjectsFailed,
      selectProject,
      canEdit,
      canRun,
      handleSaveWorkflow,
      dispatch,
      deleteCanvasNode,
      deleteCanvasConnection,
      saveCanvasConnection: saveCanvasConnectionAction,
    }
  }, [
    isNew,
    workflowId,
    workflowName,
    workflowDescription,
    selectableProjects,
    selectableProjectsLoading,
    selectableProjectsFailed,
    selectProject,
    canEdit,
    canRun,
    handleSaveWorkflow,
    dispatch,
    deleteCanvasNode,
    deleteCanvasConnection,
    saveCanvasConnectionAction,
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
