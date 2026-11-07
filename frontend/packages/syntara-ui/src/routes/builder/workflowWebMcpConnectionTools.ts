import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'
import type { Connection, ReactFlowInstance } from '@xyflow/react'

import { buildTriggerNodeId } from '../../utils/triggerNodeIds'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import type { EdgeConnection } from './types/edge'
import { EdgeFactory } from './utils/EdgeFactory'
import { getPlaceholderNodeId } from './utils/edgeHelpers'
import { validateConnection } from './utils/validateConnection'
import type { EdgeType } from './utils/workflowToGraph'
import { getAvailableSourceHandles, isEditableWorkflowNode } from './workflowWebMcpNodeTools'
import { getWorkflowSnapshot } from './workflowWebMcpState'
import type { CanvasConnectionInput, ToolDefinition, WorkflowCanvasActions } from './workflowWebMcpToolTypes'

export type ConnectionToolActions = Pick<
  WorkflowCanvasActions,
  'canEdit' | 'deleteCanvasConnection' | 'saveCanvasConnection'
>

type ResolvedSource = { node: Activity; nodeId: string; canvasNodeId: string; isTrigger: boolean }

type ResolvedConnection = {
  source: ResolvedSource
  target: Activity
  sourceHandle: string
  targetHandle: string
  edgeId?: string
}

const EDGE_ID_SCHEMA = {
  type: 'object',
  required: ['edge_id'],
  additionalProperties: false,
  properties: {
    edge_id: { type: 'string', minLength: 1, description: 'ID from the builder state connections list.' },
  },
}

const ADD_CONNECTION_SCHEMA = {
  type: 'object',
  required: ['source', 'target'],
  additionalProperties: false,
  properties: {
    source: { type: 'string', minLength: 1, description: 'Step or trigger ID from get_workflow_builder_state.' },
    target: { type: 'string', minLength: 1, description: 'Step ID from get_workflow_builder_state.' },
    source_handle: {
      type: 'string',
      minLength: 1,
      description: 'Required for branch nodes; read available handles from builder state.',
    },
    target_handle: { type: 'string', enum: [EdgeHandleEnum.TARGET, EdgeHandleEnum.END] },
  },
}

const UPDATE_CONNECTION_SCHEMA = {
  type: 'object',
  required: ['edge_id', 'source', 'target'],
  additionalProperties: false,
  properties: {
    edge_id: EDGE_ID_SCHEMA.properties.edge_id,
    source: ADD_CONNECTION_SCHEMA.properties.source,
    target: ADD_CONNECTION_SCHEMA.properties.target,
    source_handle: ADD_CONNECTION_SCHEMA.properties.source_handle,
    target_handle: ADD_CONNECTION_SCHEMA.properties.target_handle,
  },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function parseConnectionInput(input: unknown): CanvasConnectionInput | null {
  if (!isRecord(input) || typeof input.source !== 'string' || typeof input.target !== 'string') return null
  return {
    ...(typeof input.edge_id === 'string' ? { edgeId: input.edge_id } : {}),
    source: input.source,
    target: input.target,
    ...(typeof input.source_handle === 'string' ? { sourceHandle: input.source_handle } : {}),
    ...(typeof input.target_handle === 'string' ? { targetHandle: input.target_handle } : {}),
  }
}

function resolveSourceNode(sourceId: string, activities: Activity[], triggers: Activity[]): ResolvedSource | null {
  const activity = activities.find((candidate) => candidate.id === sourceId)
  if (activity) return { node: activity, nodeId: activity.id, canvasNodeId: activity.id, isTrigger: false }

  const triggerIndexById = triggers.findIndex((trigger) => trigger.id === sourceId)
  const triggerReference = /^trigger-(\d+)$/.exec(sourceId)
  const triggerIndex = triggerIndexById >= 0 ? triggerIndexById : Number(triggerReference?.[1])
  if (!Number.isInteger(triggerIndex) || triggerIndex < 0) return null
  const trigger = triggers[triggerIndex]
  return trigger
    ? {
        node: trigger,
        nodeId: trigger.id,
        canvasNodeId: buildTriggerNodeId(triggerIndex),
        isTrigger: true,
      }
    : null
}

function resolveConnectionEndpoints(
  input: CanvasConnectionInput,
  activities: Activity[],
  triggers: Activity[]
): { ok: true; source: ResolvedSource; target: Activity } | { ok: false; message: string } {
  const source = resolveSourceNode(input.source, activities, triggers)
  const target = activities.find((activity) => activity.id === input.target)
  if (!source) return { ok: false, message: `No step or trigger was found with ID "${input.source}".` }
  if (!target) return { ok: false, message: `No step was found with ID "${input.target}".` }
  if (!source.isTrigger && !isEditableWorkflowNode(source.node)) {
    return { ok: false, message: 'This source node is managed by Syntara and cannot be changed with WebMCP.' }
  }
  if (!isEditableWorkflowNode(target)) {
    return { ok: false, message: 'This target node is managed by Syntara and cannot be changed with WebMCP.' }
  }
  if (source.nodeId === target.id) return { ok: false, message: 'A node cannot connect to itself.' }
  return { ok: true, source, target }
}

function resolveSourceHandle(
  input: CanvasConnectionInput,
  source: ResolvedSource
): { ok: true; handle: string } | { ok: false; message: string } {
  const sourceHandles = getAvailableSourceHandles(source.node, source.isTrigger)
  const sourceHandle = input.sourceHandle ?? (sourceHandles.length === 1 ? sourceHandles[0] : undefined)
  if (!sourceHandle || !sourceHandles.includes(sourceHandle)) {
    return {
      ok: false,
      message: `Provide a source_handle supported by ${source.node.name ?? source.node.type}: ${sourceHandles.join(', ')}.`,
    }
  }
  return { ok: true, handle: sourceHandle }
}

function resolveTargetHandle(
  input: CanvasConnectionInput,
  target: Activity
): { ok: true; handle: string } | { ok: false; message: string } {
  const targetHandle = input.targetHandle ?? EdgeHandleEnum.TARGET
  if (targetHandle !== EdgeHandleEnum.TARGET && targetHandle !== EdgeHandleEnum.END) {
    return { ok: false, message: 'target_handle must be "target" or "end".' }
  }
  if (targetHandle === EdgeHandleEnum.END && target.type !== ActivityTypeEnum.LOOP) {
    return { ok: false, message: 'target_handle "end" is only valid when connecting back to a loop node.' }
  }
  return { ok: true, handle: targetHandle }
}

type ValidateConnectionMutationOptions = {
  input: CanvasConnectionInput
  source: ResolvedSource
  target: Activity
  sourceHandle: string
  targetHandle: string
  edges: EdgeConnection[]
  reactFlowInstance: ReactFlowInstance<NodeType, EdgeType>
}

function validateConnectionMutation({
  input,
  source,
  target,
  sourceHandle,
  targetHandle,
  edges,
  reactFlowInstance,
}: ValidateConnectionMutationOptions): string | null {
  const existingEdge = input.edgeId ? edges.find((edge) => edge.id === input.edgeId) : undefined
  if (input.edgeId && !existingEdge) {
    return `No workflow connection was found with ID "${input.edgeId}".`
  }
  const duplicate = edges.some(
    (edge) =>
      edge.id !== input.edgeId &&
      edge.source === source.nodeId &&
      edge.target === target.id &&
      (edge.sourceHandle ?? EdgeHandleEnum.SOURCE) === sourceHandle &&
      (edge.targetHandle ?? EdgeHandleEnum.TARGET) === targetHandle
  )
  if (duplicate) return 'This workflow connection already exists.'
  if (!input.edgeId && edges.length >= 100) return 'The canvas already has 100 connections.'

  const candidate: Connection = {
    source: source.canvasNodeId,
    target: target.id,
    sourceHandle,
    targetHandle,
  }
  const edgesForValidation = reactFlowInstance.getEdges().filter((edge) => edge.id !== input.edgeId)
  if (!validateConnection(candidate, edgesForValidation)) {
    return 'The builder rejected this connection. Check the selected handles and loop branch.'
  }
  return null
}

function resolveConnection(
  input: CanvasConnectionInput,
  reactFlowInstance: ReactFlowInstance<NodeType, EdgeType>
): { ok: true; value: ResolvedConnection } | { ok: false; message: string } {
  const { currentWorkflow, activities, triggers, edges } = getWorkflowSnapshot()
  if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading.' }

  const endpoints = resolveConnectionEndpoints(input, activities, triggers)
  if (!endpoints.ok) return endpoints
  const sourceHandle = resolveSourceHandle(input, endpoints.source)
  if (!sourceHandle.ok) return sourceHandle
  const targetHandle = resolveTargetHandle(input, endpoints.target)
  if (!targetHandle.ok) return targetHandle
  const validationError = validateConnectionMutation({
    input,
    source: endpoints.source,
    target: endpoints.target,
    sourceHandle: sourceHandle.handle,
    targetHandle: targetHandle.handle,
    edges,
    reactFlowInstance,
  })
  if (validationError) return { ok: false, message: validationError }

  return {
    ok: true,
    value: {
      source: endpoints.source,
      target: endpoints.target,
      sourceHandle: sourceHandle.handle,
      targetHandle: targetHandle.handle,
      ...(input.edgeId && { edgeId: input.edgeId }),
    },
  }
}

function removeConnectedSourcePlaceholder(
  source: Activity,
  canvasSourceId: string,
  sourceHandle: string,
  reactFlowInstance: ReactFlowInstance<NodeType, EdgeType>
): void {
  const placeholderId = getPlaceholderNodeId(canvasSourceId, sourceHandle)
  reactFlowInstance.setNodes((currentNodes) => {
    const nodesWithoutPlaceholder = currentNodes.filter((node) => node.id !== placeholderId)
    const sourceNode = nodesWithoutPlaceholder.find((node) => node.id === canvasSourceId)
    if (!sourceNode) return nodesWithoutPlaceholder
    if (source.type === ActivityTypeEnum.CONDITION) {
      const hasOtherPlaceholder = nodesWithoutPlaceholder.some(
        (node) =>
          node.id === getPlaceholderNodeId(canvasSourceId, EdgeHandleEnum.TRUE) ||
          node.id === getPlaceholderNodeId(canvasSourceId, EdgeHandleEnum.FALSE)
      )
      if (hasOtherPlaceholder) return nodesWithoutPlaceholder
    }
    return nodesWithoutPlaceholder.map((node) =>
      node.id === canvasSourceId
        ? { ...node, className: (node.className ?? '').replace('has-button-edge', '').trim() }
        : node
    )
  })
}

export function saveCanvasConnection(
  input: CanvasConnectionInput,
  reactFlowInstance: ReactFlowInstance<NodeType, EdgeType>
) {
  const resolution = resolveConnection(input, reactFlowInstance)
  if (!resolution.ok) return resolution
  const { source, target, sourceHandle, targetHandle, edgeId } = resolution.value
  const edge = EdgeFactory.createEdge({
    source: source.canvasNodeId,
    target: target.id,
    sourceHandle,
    targetHandle,
  })
  reactFlowInstance.setEdges((currentEdges) => {
    const withoutReplaced = currentEdges.filter((currentEdge) => currentEdge.id !== edgeId)
    const withoutButton = EdgeFactory.removeButtonEdge(source.canvasNodeId, withoutReplaced, sourceHandle)
    return EdgeFactory.addEdge(edge, withoutButton)
  })
  removeConnectedSourcePlaceholder(source.node, source.canvasNodeId, sourceHandle, reactFlowInstance)

  return {
    ok: true as const,
    connection: {
      id: edge.id,
      source: source.nodeId,
      target: target.id,
      sourceHandle,
      targetHandle,
    },
  }
}

function createGetWorkflowConnectionTool(): ToolDefinition {
  return {
    name: 'get_workflow_connection',
    description: 'Read one workflow connection by edge_id from get_workflow_builder_state.',
    inputSchema: EDGE_ID_SCHEMA,
    annotations: { readOnlyHint: true, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      const { currentWorkflow, edges } = getWorkflowSnapshot()
      if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading.' }
      if (!isRecord(input) || typeof input.edge_id !== 'string' || !input.edge_id.trim()) {
        return { ok: false, message: 'Provide an edge_id from get_workflow_builder_state.' }
      }
      const edge = edges.find((candidate) => candidate.id === input.edge_id)
      return edge
        ? { ok: true, connection: edge }
        : { ok: false, message: `No workflow connection was found with ID "${input.edge_id}".` }
    },
  }
}

function createAddWorkflowConnectionTool(actionsRef: { current: ConnectionToolActions }): ToolDefinition {
  return {
    name: 'add_workflow_connection',
    description:
      'Connect a step or trigger to a step on the open workflow canvas. Use IDs and source_handles from get_workflow_builder_state. Branch nodes require a source_handle; target_handle is target by default, or end for a loop-back edge. This edits the draft only.',
    inputSchema: ADD_CONNECTION_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      if (!actionsRef.current.canEdit)
        return { ok: false, message: 'You do not have permission to edit this workflow.' }
      const connection = parseConnectionInput(input)
      if (!connection) return { ok: false, message: 'Provide source and target node IDs.' }
      const result = actionsRef.current.saveCanvasConnection(connection)
      return result.ok
        ? { ok: true, saved: false, connection: result.connection, message: 'Added the workflow connection.' }
        : result
    },
  }
}

function createUpdateWorkflowConnectionTool(actionsRef: { current: ConnectionToolActions }): ToolDefinition {
  return {
    name: 'update_workflow_connection',
    description:
      'Change a workflow connection’s endpoints or handles by edge_id. Provide source and target IDs from get_workflow_builder_state. Omitted handles keep the existing handle when its endpoint is unchanged; otherwise standard handles are selected where possible. This edits the draft only.',
    inputSchema: UPDATE_CONNECTION_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: true, consequentialHint: false },
    execute: (input) => {
      if (!actionsRef.current.canEdit)
        return { ok: false, message: 'You do not have permission to edit this workflow.' }
      if (!isRecord(input) || typeof input.edge_id !== 'string' || !input.edge_id.trim()) {
        return { ok: false, message: 'Provide an edge_id from get_workflow_builder_state.' }
      }
      const current = getWorkflowSnapshot().edges.find((edge) => edge.id === input.edge_id)
      if (!current) return { ok: false, message: `No workflow connection was found with ID "${input.edge_id}".` }
      const connection = parseConnectionInput(input)
      if (!connection) return { ok: false, message: 'Provide source and target node IDs.' }
      const result = actionsRef.current.saveCanvasConnection({
        ...connection,
        edgeId: current.id,
        sourceHandle:
          connection.sourceHandle ??
          (connection.source === current.source ? (current.sourceHandle ?? undefined) : undefined),
        targetHandle:
          connection.targetHandle ??
          (connection.target === current.target ? (current.targetHandle ?? undefined) : undefined),
      })
      return result.ok
        ? { ok: true, saved: false, connection: result.connection, message: 'Updated the workflow connection.' }
        : result
    },
  }
}

function createDeleteWorkflowConnectionTool(actionsRef: { current: ConnectionToolActions }): ToolDefinition {
  return {
    name: 'delete_workflow_connection',
    description: 'Delete one workflow connection by edge_id. This edits the draft only.',
    inputSchema: EDGE_ID_SCHEMA,
    annotations: { readOnlyHint: false, untrustedContentHint: false, consequentialHint: false },
    execute: async (input) => {
      if (!actionsRef.current.canEdit)
        return { ok: false, message: 'You do not have permission to edit this workflow.' }
      if (!isRecord(input) || typeof input.edge_id !== 'string' || !input.edge_id.trim()) {
        return { ok: false, message: 'Provide an edge_id from get_workflow_builder_state.' }
      }
      const { currentWorkflow, edges } = getWorkflowSnapshot()
      if (!currentWorkflow) return { ok: false, message: 'The workflow builder is still loading.' }
      if (!edges.some((edge) => edge.id === input.edge_id)) {
        return { ok: false, message: `No workflow connection was found with ID "${input.edge_id}".` }
      }
      const deleted = await actionsRef.current.deleteCanvasConnection(input.edge_id)
      return deleted
        ? { ok: true, saved: false, deleted_edge_id: input.edge_id, message: 'Deleted the workflow connection.' }
        : { ok: false, message: 'The canvas did not confirm deletion of this connection.' }
    },
  }
}

export function createWorkflowConnectionTools(actionsRef: { current: ConnectionToolActions }): ToolDefinition[] {
  const tools = [createGetWorkflowConnectionTool()]
  if (actionsRef.current.canEdit) {
    tools.push(
      createAddWorkflowConnectionTool(actionsRef),
      createUpdateWorkflowConnectionTool(actionsRef),
      createDeleteWorkflowConnectionTool(actionsRef)
    )
  }
  return tools
}
