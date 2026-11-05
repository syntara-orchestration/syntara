import { ActivityTypeEnum, EdgeHandleEnum, type Activity } from '@syntara/contracts'
import { useMemo } from 'react'

import { FlowNodeType } from '../../../constants'
import { buildTriggerNodeId } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeConnection } from '../types/edge'
import { ExecutionStateEnricher, type ActivityWithMetadata } from '../utils/executionState'
import { extractTaskActivities, getTriggerDisplayData, type EdgeType, type Trigger } from '../utils/workflowToGraph'

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
  workflowVersion: number
}

export { executionStateEnricher }

export function useBuilderFlowGraph({
  currentWorkflow,
  triggers,
  activities: activitiesFromStore,
  storedEdges,
  workflowVersion,
}: UseBuilderFlowGraphParams) {
  return useMemo(() => {
    if (!currentWorkflow) {
      return { nodes: [] as NodeType[], edges: [] as EdgeType[] }
    }

    const nodes: NodeType[] = []
    const edges: EdgeType[] = []
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
      nodes.push({
        id: triggerId,
        type: 'trigger',
        position: { x: 0, y: 0 },
        data: triggerData,
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

      nodes.push({
        id: activity.id,
        type: activity.type,
        position: { x: 0, y: 0 },
        data: activity,
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

      const node = {
        id: activity.id,
        type: nodeType,
        position,
        data: activity,
      } as unknown as NodeType

      nodes.push(node)
    })

    return { nodes, edges }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowVersion, currentWorkflow?.inputs, triggers, activitiesFromStore, storedEdges])
}
