import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'

import { getActivityMetadata } from '../../stores/useWorkflowStore'
import { getErrorMessage } from '../../utils/apiErrors'

import { WEBMCP_WORKFLOW_NODE_TYPES } from './workflowWebMcp'
import { buildWorkflowNodeActivity, buildWorkflowNodeUpdate } from './workflowWebMcpNodeBuilder'
import { getWorkflowSnapshot } from './workflowWebMcpState'
import type { ToolDefinition, WorkflowCanvasActions } from './workflowWebMcpToolTypes'

export type NodeToolActions = Pick<WorkflowCanvasActions, 'canEdit' | 'deleteCanvasNode'>

const NODE_ID_SCHEMA = {
  type: 'object',
  required: ['node_id'],
  additionalProperties: false,
  properties: {
    node_id: { type: 'string', minLength: 1, description: 'ID from the builder state steps list.' },
  },
}

const NODE_SETTINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    disabled: { type: 'boolean' },
    continue_on_failure: { type: 'boolean' },
    timeout: { type: 'number', minimum: 0 },
    retry_policy: {
      type: 'object',
      additionalProperties: false,
      properties: {
        max_retries: { type: 'integer', minimum: 0 },
        backoff: { type: 'string', enum: ['exponential', 'fixed'] },
        initial_interval: { type: 'number', minimum: 0 },
        max_interval: { type: 'number', minimum: 0 },
        backoff_coefficient: { type: 'number', minimum: 0 },
      },
    },
  },
}

const ADD_NODE_SCHEMA = {
  type: 'object',
  required: ['type', 'name'],
  additionalProperties: false,
  properties: {
    type: { type: 'string', enum: WEBMCP_WORKFLOW_NODE_TYPES },
    name: { type: 'string', minLength: 1, maxLength: 255 },
    parameters: {
      type: 'object',
      additionalProperties: true,
      description: 'Node parameters in Syntara backend format. Use credential references, never secret values.',
    },
    settings: NODE_SETTINGS_SCHEMA,
  },
}

const UPDATE_NODE_SCHEMA = {
  type: 'object',
  required: ['node_id'],
  additionalProperties: false,
  properties: {
    ...NODE_ID_SCHEMA.properties,
    type: { type: 'string', enum: WEBMCP_WORKFLOW_NODE_TYPES },
    name: { type: 'string', minLength: 1, maxLength: 255 },
    parameters: {
      type: 'object',
      additionalProperties: true,
      description: 'Replace all node parameters. Required when changing the node type.',
    },
    parameters_patch: {
      type: 'object',
      additionalProperties: true,
      description: 'Merge fields into node parameters. Existing fields are kept unless overwritten.',
    },
    settings_patch: {
      ...NODE_SETTINGS_SCHEMA,
      description: 'Settings to merge into the node settings.',
    },
  },
}

const EDITABLE_NODE_TYPES = new Set<string>(WEBMCP_WORKFLOW_NODE_TYPES)
const REDACTED_NODE_FIELD = /password|secret|token|authorization|api[_-]?key|cookie|credential|private[_-]?key/i

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function isEditableWorkflowNode(activity: Activity): boolean {
  return EDITABLE_NODE_TYPES.has(activity.type) && getActivityMetadata(activity)?.__isGeneric !== true
}

export function getAvailableSourceHandles(activity: Activity, isTrigger = false): string[] {
  if (isTrigger) return [EdgeHandleEnum.SOURCE]
  switch (activity.type) {
    case ActivityTypeEnum.CONDITION:
      return [EdgeHandleEnum.TRUE, EdgeHandleEnum.FALSE]
    case ActivityTypeEnum.APPROVAL:
      return [EdgeHandleEnum.APPROVED, EdgeHandleEnum.REJECTED]
    case ActivityTypeEnum.LOOP:
      return [EdgeHandleEnum.DONE, EdgeHandleEnum.LOOP]
    case ActivityTypeEnum.SWITCH: {
      const cases = activity.parameters?.cases
      const caseHandles = Array.isArray(cases)
        ? cases.flatMap((item) =>
            isRecord(item) && typeof item.port === 'string' && /^case_\d+$/.test(item.port) ? [item.port] : []
          )
        : []
      if (
        activity.parameters?.default_port === undefined ||
        activity.parameters.default_port === EdgeHandleEnum.DEFAULT
      ) {
        caseHandles.push(EdgeHandleEnum.DEFAULT)
      }
      return caseHandles.length > 0 ? caseHandles : [EdgeHandleEnum.DEFAULT]
    }
    default:
      return [EdgeHandleEnum.SOURCE]
  }
}

function redactNodeValue(value: unknown, key = '', depth = 0): unknown {
  if (key && REDACTED_NODE_FIELD.test(key)) return '[redacted]'
  if (depth > 8) return '[truncated]'
  if (typeof value === 'string') return value.length > 4000 ? `${value.slice(0, 4000)}…[truncated]` : value
  if (Array.isArray(value)) return value.slice(0, 100).map((item) => redactNodeValue(item, '', depth + 1))
  if (isRecord(value)) {
    const sensitiveLabel = [value.key, value.name].some(
      (label) => typeof label === 'string' && REDACTED_NODE_FIELD.test(label)
    )
    return Object.fromEntries(
      Object.entries(value)
        .slice(0, 100)
        .map(([childKey, childValue]) => [
          childKey,
          sensitiveLabel && childKey === 'value' ? '[redacted]' : redactNodeValue(childValue, childKey, depth + 1),
        ])
    )
  }
  return value
}

function createGetWorkflowNodeTool(): ToolDefinition {
  return {
    name: 'get_workflow_node',
    description:
      'Read one step node from the open workflow builder by node_id. Returns its name, type, settings, and parameters with credential- and secret-shaped fields redacted.',
    inputSchema: NODE_ID_SCHEMA,
    annotations: { readOnlyHint: true, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      const { currentWorkflow, activities } = getWorkflowSnapshot()
      if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading.' }
      if (!isRecord(input) || typeof input.node_id !== 'string' || !input.node_id.trim()) {
        return { ok: false, message: 'Provide a node_id from get_workflow_builder_state.' }
      }
      const activity = activities.find((candidate) => candidate.id === input.node_id)
      if (!activity) return { ok: false, message: `No workflow node was found with ID "${input.node_id}".` }
      return {
        ok: true,
        node: {
          id: activity.id,
          type: activity.type,
          name: activity.name,
          editable: isEditableWorkflowNode(activity),
          source_handles: getAvailableSourceHandles(activity),
          parameters: redactNodeValue(activity.parameters ?? {}),
          settings: redactNodeValue(activity.settings ?? {}),
        },
      }
    },
  }
}

function createAddWorkflowNodeTool(actionsRef: { current: NodeToolActions }): ToolDefinition {
  return {
    name: 'add_workflow_node',
    description:
      'Add one user-selectable step node to the open workflow canvas. This adds a draft node only; connect it, validate, and save separately. Parameters use backend keys and must not contain secret values.',
    inputSchema: ADD_NODE_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      if (!actionsRef.current.canEdit)
        return { ok: false, message: 'You do not have permission to edit this workflow.' }
      const { currentWorkflow, store } = getWorkflowSnapshot()
      if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading.' }
      try {
        const activity = buildWorkflowNodeActivity(input)
        store.addActivity(activity)
        return {
          ok: true,
          saved: false,
          node: { id: activity.id, type: activity.type, name: activity.name },
          message: `Added ${activity.name} to the canvas. Connect it to the workflow, validate, and save.`,
        }
      } catch (error) {
        return { ok: false, message: getErrorMessage(error) }
      }
    },
  }
}

function createUpdateWorkflowNodeTool(actionsRef: { current: NodeToolActions }): ToolDefinition {
  return {
    name: 'update_workflow_node',
    description:
      'Update a step node name, type, parameters, or settings. Use parameters to replace all configuration, or parameters_patch/settings_patch to merge fields. Changing type requires parameters. Use get_workflow_node first when you need to inspect current values. This edits the draft only.',
    inputSchema: UPDATE_NODE_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      const actions = actionsRef.current
      if (!actions.canEdit) return { ok: false, message: 'You do not have permission to edit this workflow.' }
      if (!isRecord(input) || typeof input.node_id !== 'string' || !input.node_id.trim()) {
        return { ok: false, message: 'Provide a node_id from get_workflow_builder_state.' }
      }
      const { currentWorkflow, activities, store } = getWorkflowSnapshot()
      if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading.' }
      const activity = activities.find((candidate) => candidate.id === input.node_id)
      if (!activity) return { ok: false, message: `No workflow node was found with ID "${input.node_id}".` }
      if (!isEditableWorkflowNode(activity)) {
        return { ok: false, message: 'This node is managed by Syntara and cannot be edited with WebMCP.' }
      }
      try {
        const updates = buildWorkflowNodeUpdate(activity, input)
        if (updates.type && updates.type !== activity.type) {
          store.replaceActivity(activity.id, { ...activity, ...updates })
        } else {
          store.updateActivity(activity.id, updates)
        }
        return {
          ok: true,
          saved: false,
          node: { id: activity.id, type: updates.type ?? activity.type, name: updates.name ?? activity.name },
          message: 'Updated the node on the canvas. Validate and save to persist the change.',
        }
      } catch (error) {
        return { ok: false, message: getErrorMessage(error) }
      }
    },
  }
}

function createDeleteWorkflowNodeTool(actionsRef: { current: NodeToolActions }): ToolDefinition {
  return {
    name: 'delete_workflow_node',
    description:
      'Delete a user-selectable step node from the canvas by node_id. Syntara removes its connected edges and handles loop-body cleanup. This edits the draft only.',
    inputSchema: NODE_ID_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: false, consequentialHint: false },
    execute: async (input) => {
      const actions = actionsRef.current
      if (!actions.canEdit) return { ok: false, message: 'You do not have permission to edit this workflow.' }
      if (!isRecord(input) || typeof input.node_id !== 'string' || !input.node_id.trim()) {
        return { ok: false, message: 'Provide a node_id from get_workflow_builder_state.' }
      }
      const { currentWorkflow, activities } = getWorkflowSnapshot()
      if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading.' }
      const activity = activities.find((candidate) => candidate.id === input.node_id)
      if (!activity) return { ok: false, message: `No workflow node was found with ID "${input.node_id}".` }
      if (!isEditableWorkflowNode(activity)) {
        return { ok: false, message: 'This node is managed by Syntara and cannot be deleted with WebMCP.' }
      }
      try {
        const deletedNodeIds = await actions.deleteCanvasNode(activity.id)
        return deletedNodeIds.includes(activity.id)
          ? { ok: true, saved: false, deleted_node_ids: deletedNodeIds, message: `Deleted node ${activity.name}.` }
          : { ok: false, message: 'The canvas did not confirm deletion of this node.' }
      } catch (error) {
        return { ok: false, message: getErrorMessage(error) }
      }
    },
  }
}

export function createWorkflowNodeTools(actionsRef: { current: NodeToolActions }): ToolDefinition[] {
  const tools = [createGetWorkflowNodeTool()]
  if (actionsRef.current.canEdit) {
    tools.push(
      createAddWorkflowNodeTool(actionsRef),
      createUpdateWorkflowNodeTool(actionsRef),
      createDeleteWorkflowNodeTool(actionsRef)
    )
  }
  return tools
}
