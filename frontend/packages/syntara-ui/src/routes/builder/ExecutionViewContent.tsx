import type { Activity, ExecutionsAPI } from '@syntara/contracts'
import type { NodeMouseHandler } from '@xyflow/react'
import { ReactFlowProvider } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useRef } from 'react'

import { SynPanel } from '../../components/layout/SynPanel'
import { useWorkflowStoreActions } from '../../stores/useWorkflowStore'
import { buildTriggerNodeId } from '../../utils/triggerNodeIds'
import { useExecutionStoreActions } from '../workflows/stores/useExecutionStore'

import { BuilderFlow } from './BuilderFlow'
import { ExecutionViewContext } from './ExecutionViewContext'
import type { EdgeConnection } from './types/edge'
import { v2PortToHandle, v2TargetPortToHandle } from './utils/edgeHelpers'
import { parseNodePositions } from './utils/processExistingWorkflow'

type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

/** Activity data from Execution.activities (ActivityData) or list endpoint (ActivityExecution) */
type ActivityInput = ActivityData | ActivityExecution

/** Accepts both full Workflow objects and execution-derived workflow data with version.workflow_definition */
type ExecutionWorkflow = {
  id: string
  name?: string
  version?: { workflow_definition?: unknown }
  workflow?: { activities?: Activity[] }
  triggers?: unknown[]
}

type ExecutionViewContentProps = {
  workflow?: ExecutionWorkflow
  executionStatus?: string | null
  executionActivities?: ActivityInput[]
  executionId: string
  /** Optional handler for node clicks (e.g., approval nodes in waiting status). */
  onNodeClick?: NodeMouseHandler
  /** Activity ID of the externally selected node (e.g. from table row click). */
  selectedActivityId?: string | null
}

/**
 * Inner component that has access to React Flow instance
 * Handles workflow loading and execution state synchronization
 */
function ExecutionViewContentInner(props: ExecutionViewContentProps) {
  const { workflow, executionStatus, executionActivities, executionId, onNodeClick, selectedActivityId } = props
  const { loadWorkflowWithEdges, setWorkflow: setWorkflowInStore, setEdges: setStoredEdges } = useWorkflowStoreActions()
  const { setActivityExecutions } = useExecutionStoreActions()
  const hasLoadedRef = useRef(false)
  const hasLoadedActivitiesRef = useRef(false)
  const prevWorkflowIdRef = useRef<string | null>(null)
  const prevExecutionIdRef = useRef<string | null>(null)

  // Load execution activities into execution store
  useEffect(() => {
    const workflowId = workflow?.id ?? null

    if (prevWorkflowIdRef.current !== workflowId || prevExecutionIdRef.current !== executionId) {
      hasLoadedActivitiesRef.current = false
      prevExecutionIdRef.current = executionId
    }

    if (executionActivities && executionActivities.length > 0 && !hasLoadedActivitiesRef.current) {
      setActivityExecutions(executionActivities)
      hasLoadedActivitiesRef.current = true
    }
  }, [executionActivities, setActivityExecutions, workflow, executionId])

  // Load workflow into store
  useEffect(() => {
    const workflowId = workflow?.id ?? null

    // Reset when workflow ID OR execution ID changes
    if (prevWorkflowIdRef.current !== workflowId || prevExecutionIdRef.current !== executionId) {
      setWorkflowInStore(null)
      setStoredEdges([])
      hasLoadedRef.current = false
      prevWorkflowIdRef.current = workflowId
      prevExecutionIdRef.current = executionId
    }

    // Only load workflow after activities are loaded (or if there are none to load)
    const canLoadWorkflow = !executionActivities || executionActivities.length === 0 || hasLoadedActivitiesRef.current

    // Load the workflow if we have one and haven't loaded it yet
    if (workflow && !hasLoadedRef.current && canLoadWorkflow) {
      // Extract workflow definition - handle both direct workflow and version.workflow_definition structures
      const workflowDef = (workflow.version?.workflow_definition ?? workflow) as ExecutionWorkflow

      // V2: workflow definition has nodes/edges/triggers at top level
      const v2Def = workflowDef as unknown as Record<string, unknown>
      const nodes = (v2Def.nodes ??
        (v2Def.workflow as Record<string, unknown> | undefined)?.activities ??
        []) as Activity[]
      const v2Edges = (v2Def.edges ?? []) as Array<{ from: string; to: string; from_port?: string; to_port?: string }>
      const triggers = (v2Def.triggers ?? []) as Array<{
        id?: string
        type: string
        name?: string
        config?: Record<string, unknown>
      }>

      if (nodes.length === 0 && triggers.length === 0) {
        return
      }

      // V2 activities are already flat — no nesting to flatten
      const flattenedActivities = nodes

      // Build map: trigger definition ID → React Flow display ID
      const triggerIdToDisplayId = new Map<string, string>()
      triggers.forEach((t, index: number) => {
        const defId = (t as { id?: string }).id
        if (defId) {
          triggerIdToDisplayId.set(defId, buildTriggerNodeId(index))
        }
      })

      // Convert v2 edges to React Flow edges, mapping trigger IDs to display IDs
      const generatedEdges: EdgeConnection[] = v2Edges.map((e) => {
        const source = triggerIdToDisplayId.get(e.from) ?? e.from
        const target = triggerIdToDisplayId.get(e.to) ?? e.to
        const portSuffix = e.from_port ? `-${e.from_port}` : ''
        return {
          id: `${source}-${target}${portSuffix}`,
          source,
          target,
          sourceHandle: v2PortToHandle(e.from_port),
          targetHandle: v2TargetPortToHandle(e.to_port),
        }
      })

      // Build store workflow from v2 definition
      const storeWorkflow = {
        schema_version: '2.0.0' as const,
        name: (v2Def.name as string) ?? '',
        description: v2Def.description as string | undefined,
        triggers,
        workflow: {
          activities: flattenedActivities,
        },
      }

      // Extract positions from raw nodes/triggers so the canvas matches saved layout
      const rawNodesForPositions = nodes as unknown as Array<Record<string, unknown>>
      const rawTriggersForPositions = triggers as unknown as Array<Record<string, unknown>>
      const nodePositions = parseNodePositions([...rawNodesForPositions, ...rawTriggersForPositions])

      // Load workflow and edges into store (with positions to prevent re-layout on return)
      queueMicrotask(() => {
        loadWorkflowWithEdges(
          storeWorkflow as unknown as Parameters<typeof loadWorkflowWithEdges>[0],
          generatedEdges,
          nodePositions
        )
        hasLoadedRef.current = true
      })
    }
  }, [workflow, loadWorkflowWithEdges, setWorkflowInStore, setStoredEdges, executionActivities, executionId])

  return (
    <SynPanel
      hasNoPadding
      isFullHeight
      style={{
        position: 'relative',
        minWidth: 0,
        width: '100%',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <BuilderFlow
        workflowId={workflow?.id ?? null}
        panelOpen={false}
        activeEdgeButtonNodeId={null}
        activeEdgeButtonHandle={null}
        activeEdgeId={null}
        executionStatus={executionStatus}
        onNodeClick={onNodeClick}
        selectedActivityId={selectedActivityId}
        onAddNodeFromEdge={() => {
          // No-op: cannot add steps in execution view
        }}
        onNodesDeleted={() => {
          // No-op: cannot delete steps in execution view
        }}
      />
    </SynPanel>
  )
}

/**
 * Read-only execution view component
 * Renders workflow execution visualization without any editing features
 *
 * Key differences from BuilderContent:
 * - No AddNodePanel
 * - No NodeDetailsPanel
 * - No WorkflowSidepanel
 * - No save/run buttons
 * - Node clicks only for approval nodes in waiting status (via onNodeClick prop)
 * - No edge button creation
 */
export function ExecutionViewContent(props: ExecutionViewContentProps) {
  return (
    <ExecutionViewContext.Provider value={true}>
      <ReactFlowProvider>
        <ExecutionViewContentInner {...props} />
      </ReactFlowProvider>
    </ExecutionViewContext.Provider>
  )
}
