import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'
import { useMemo } from 'react'

import { FlowNodeType } from '../../../constants'
import { buildTriggerNodeId } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../../workflows/execution/types'
import type { EdgeConnection } from '../types/edge'
import { detectLoopBackNodes } from '../utils/detectLoopBackNodes'
import { ExecutionStateEnricher, type ActivityWithMetadata } from '../utils/executionState'
import {
  extractTaskActivities,
  getTriggerDisplayData,
  markerEnd,
  type EdgeType,
  type Trigger,
} from '../utils/workflowToGraph'

import { applyLoopBackNodeTypes } from './useLoopBackNodeTypes'

const executionStateEnricher = new ExecutionStateEnricher()

type UseBuilderFlowGraphParams = {
  currentWorkflow: {
    inputs?: Record<string, unknown>
    workflow: { activities: Activity[] }
    triggers?: Trigger[]
  } | null
  triggers: Trigger[] | undefined
  activities: Activity[] | undefined
  storedEdges: EdgeConnection[]
  executionStatus: string | null | undefined
  activityStates: Map<string, ActivityState>
  onAddNodeFromEdge: ((sourceNodeId: string, sourceHandle: string) => void) | undefined
  workflowVersion: number
  preResolvedNodes?: Set<string>
  skipInferenceActivityIds?: ReadonlySet<string> | null
}

export { executionStateEnricher }

export function useBuilderFlowGraph({
  currentWorkflow,
  triggers,
  activities: activitiesFromStore,
  storedEdges,
  executionStatus,
  activityStates,
  onAddNodeFromEdge,
  workflowVersion,
  preResolvedNodes,
  skipInferenceActivityIds,
}: UseBuilderFlowGraphParams) {
  return useMemo(() => {
    if (!currentWorkflow) {
      return { nodes: [] as NodeType[], edges: [] as EdgeType[] }
    }

    const nodes: NodeType[] = []
    const edges: EdgeType[] = []
    const inferenceAllowlist = skipInferenceActivityIds ?? undefined

    // Build mapping from real trigger IDs to display IDs (trigger-0, trigger-1, ...)
    // Edges from backend use real IDs; React Flow needs display IDs
    const triggerRealIdToDisplayId = new Map<string, string>()
    const triggersList = triggers ?? []
    triggersList.forEach((trigger: Trigger, index: number) => {
      const triggerId = buildTriggerNodeId(index)
      const { name, details } = getTriggerDisplayData(trigger)
      const triggerData = {
        name,
        details,
        triggerType: trigger.type,
        inputs: currentWorkflow?.inputs ?? {},
        definitionId: trigger.id,
      }
      const enrichedTriggerData = executionStateEnricher.enrichTriggerNode(
        trigger.id,
        triggerData,
        executionStatus,
        activityStates
      )
      nodes.push({
        id: triggerId,
        type: 'trigger',
        position: { x: 0, y: 0 },
        data: enrichedTriggerData,
      })
      // Map real trigger ID to display ID for edge transformation
      if (trigger.id) {
        triggerRealIdToDisplayId.set(trigger.id, triggerId)
      }
    })

    const activities = currentWorkflow?.workflow.activities ?? []

    activities.forEach((activity: Activity) => {
      if (
        activity.type !== ActivityTypeEnum.CONVERGE &&
        activity.type !== ActivityTypeEnum.CONDITION &&
        activity.type !== ActivityTypeEnum.LOOP &&
        activity.type !== ActivityTypeEnum.SWITCH &&
        activity.type !== ActivityTypeEnum.WAIT
      ) {
        return
      }

      const activityData = executionStateEnricher.enrichActivity(
        activity,
        executionStatus,
        activityStates,
        storedEdges,
        {
          preResolvedNodes,
          skipInferenceActivityIds: inferenceAllowlist,
        }
      )
      nodes.push({
        id: activity.id,
        type: activity.type,
        position: { x: 0, y: 0 },
        data: activityData,
      } as unknown as NodeType)
    })

    storedEdges.forEach(
      (edge: {
        id: string
        source: string
        target: string
        sourceHandle?: string | null
        targetHandle?: string | null
      }) => {
        let edgeType: string = 'default'
        if (edge.targetHandle === EdgeHandleEnum.END) {
          edgeType = 'loopBack'
        } else if (edge.sourceHandle === EdgeHandleEnum.LOOP) {
          edgeType = 'loopOutgoing'
        }

        let edgeExecutionStatus: 'passed' | 'pending' | undefined
        if (executionStatus) {
          edgeExecutionStatus = executionStateEnricher.determineEdgeStatus(
            edge,
            activityStates,
            activities,
            undefined,
            storedEdges
          )
        }

        // Transform trigger real IDs to display IDs for React Flow
        // Edges from backend use real IDs (activity_fb2060fd_...),
        // but React Flow nodes use display IDs (trigger-0, trigger-1, ...)
        const source = triggerRealIdToDisplayId.get(edge.source) ?? edge.source
        const target = triggerRealIdToDisplayId.get(edge.target) ?? edge.target

        edges.push({
          id: edge.id,
          source,
          target,
          sourceHandle: edge.sourceHandle ?? undefined,
          targetHandle: edge.targetHandle ?? undefined,
          type: edgeType,
          markerEnd,
          data: {
            onAddNode: onAddNodeFromEdge,
            executionStatus: edgeExecutionStatus,
          },
        })
      }
    )

    const taskActivities = extractTaskActivities(activities)

    taskActivities.forEach((activity: Activity) => {
      const isGeneric = (activity as ActivityWithMetadata).metadata?.__isGeneric === true
      const isApproval = activity.type === ActivityTypeEnum.APPROVAL

      const position = { x: 0, y: 0 }

      let nodeType: typeof FlowNodeType.GENERIC | typeof FlowNodeType.APPROVAL | typeof FlowNodeType.TASK =
        FlowNodeType.TASK
      if (isGeneric) {
        nodeType = FlowNodeType.GENERIC
      } else if (isApproval) {
        nodeType = FlowNodeType.APPROVAL
      }

      const activityData = executionStateEnricher.enrichActivity(
        activity,
        executionStatus,
        activityStates,
        storedEdges,
        {
          preResolvedNodes,
          skipInferenceActivityIds: inferenceAllowlist,
        }
      )

      const node = {
        id: activity.id,
        type: nodeType,
        position,
        data: activityData,
      } as unknown as NodeType

      nodes.push(node)
    })

    const loopBackNodeIds = detectLoopBackNodes(edges, nodes)
    const finalNodes = applyLoopBackNodeTypes(nodes, loopBackNodeIds)

    return { nodes: finalNodes, edges }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    workflowVersion,
    currentWorkflow?.inputs,
    triggers,
    activitiesFromStore,
    storedEdges,
    onAddNodeFromEdge,
    activityStates,
    executionStatus,
    preResolvedNodes,
    skipInferenceActivityIds,
  ])
}
