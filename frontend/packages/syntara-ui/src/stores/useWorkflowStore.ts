import { ActivityTypeEnum } from '@syntara/contracts'
import { temporal } from 'zundo'
import type { TemporalState } from 'zundo'
import { create } from 'zustand'
import type { Mutate, StoreApi } from 'zustand'
import type { UseBoundStore } from 'zustand/react'

import { buildTriggerIndexRemappping, remapTriggerIdsInEdges } from '../routes/builder/utils/triggerIndexRemapping'
import { generateActivityId } from '../utils/generateUUID'

import {
  findActivityById,
  getValidSourceHandles,
  remapSwitchEdges,
  removeActivityFromList,
  reorderActivities,
  replaceActivityInList,
  updateActivityInList,
} from './workflowActivityHelpers'
import { edgesEqual, workflowEqual } from './workflowStoreEquality'
import type { Activity, WorkflowStore } from './workflowStoreTypes'

/** Partialize shape passed to zundo — must match `temporal({ partialize })` below. */
type WorkflowUndoPartialize = Pick<WorkflowStore, 'currentWorkflow' | 'edges' | 'nodePositions'>

/** Bound store including zundo’s `temporal` API (explicit so ESLint/tsserver always see `.temporal`). */
export type UseWorkflowStoreBound = UseBoundStore<
  Mutate<StoreApi<WorkflowStore>, [['temporal', StoreApi<TemporalState<WorkflowUndoPartialize>>]]>
>

const HISTORY_LIMIT = 50
const TEMPORAL_BATCH_SAFETY_MS = 2000
const CLEAN_UNDO_STATE = { isDirty: false, _undoBaselineMatchesSave: true, _nonTemporalDirty: false } as const

/**
 * Pause temporal tracking so that the node mutation AND the subsequent
 * derived edge-sync collapse into a single undo entry.
 * The edge sync resumes tracking when it pushes edges (see
 * `useEdgeSynchronization`); a safety timeout guarantees resume even if
 * the sync never fires.
 */
let batchSafetyTimerId: ReturnType<typeof setTimeout> | null = null

function beginTemporalBatch(set: (partial: Partial<WorkflowStore>) => void) {
  useWorkflowStore.temporal.getState().pause()
  set({ _temporalBatchPending: true })
  if (batchSafetyTimerId !== null) clearTimeout(batchSafetyTimerId)
  batchSafetyTimerId = setTimeout(() => {
    batchSafetyTimerId = null
    const { _temporalBatchPending } = useWorkflowStore.getState()
    if (_temporalBatchPending) {
      useWorkflowStore.setState({ _temporalBatchPending: false })
      useWorkflowStore.temporal.getState().resume()
    }
  }, TEMPORAL_BATCH_SAFETY_MS)
}

export const useWorkflowStore: UseWorkflowStoreBound = create<WorkflowStore>()(
  temporal(
    // eslint-disable-next-line max-lines-per-function
    (set, get) => ({
      currentWorkflow: null,
      projectId: null,
      workflowVersion: 0,
      edges: [],
      nodePositions: {},
      _positionUndoVersion: 0,
      _temporalBatchPending: false,
      _preserveHistoryOnLayout: false,
      _positionsUserModified: false,
      ...CLEAN_UNDO_STATE,
      validationErrorCount: 0,

      setValidationErrorCount: (count) => set({ validationErrorCount: count }),

      setWorkflow: (workflow, projectId) => {
        set((state) => ({
          currentWorkflow: workflow,
          projectId: projectId ?? null,
          workflowVersion: state.workflowVersion + 1,
          nodePositions: {},
          _positionsUserModified: false,
          ...CLEAN_UNDO_STATE,
          validationErrorCount: 0,
        }))
        useWorkflowStore.temporal.getState().clear()
      },

      loadWorkflowWithEdges: (workflow, edges, nodePositions, projectId) => {
        set((state) => ({
          currentWorkflow: workflow,
          projectId: projectId ?? null,
          workflowVersion: state.workflowVersion + 1,
          edges,
          nodePositions: nodePositions ?? {},
          _positionsUserModified: nodePositions != null && Object.keys(nodePositions).length > 0,
          _preserveHistoryOnLayout: false,
          ...CLEAN_UNDO_STATE,
          validationErrorCount: 0,
        }))
        useWorkflowStore.temporal.getState().clear()
      },

      replaceWorkflowContent: (workflow, edges, nodePositions) => {
        const hasPositions = nodePositions != null && Object.keys(nodePositions).length > 0
        set((state) => ({
          currentWorkflow: workflow,
          workflowVersion: state.workflowVersion + 1,
          edges,
          nodePositions: nodePositions ?? {},
          _positionsUserModified: hasPositions,
          isDirty: true,
          _preserveHistoryOnLayout: true,
          validationErrorCount: 0,
        }))
        // Pause immediately so post-layout edge syncs don't create extra undo entries.
        // Resumed by clearUndoHistory in BuilderFlow after layout settles.
        useWorkflowStore.temporal.getState().pause()
      },

      markClean: () => {
        set({ isDirty: false, _undoBaselineMatchesSave: false, _nonTemporalDirty: false })
      },

      markDirty: () => {
        set({ isDirty: true, _nonTemporalDirty: true })
      },

      updateWorkflow: (updater) => {
        set((state) => {
          if (!state.currentWorkflow) return state
          return {
            currentWorkflow: updater(state.currentWorkflow),
            isDirty: true,
          }
        })
      },

      setEdges: (edges) => {
        set({ edges, isDirty: true })
      },

      addTrigger: (trigger) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          const triggers = state.currentWorkflow.triggers ?? []
          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              triggers: [...triggers, trigger],
            },
            isDirty: true,
          }
        })
      },

      removeTrigger: (index) => {
        set((state) => {
          if (!state.currentWorkflow?.triggers) return state

          const triggers = [...state.currentWorkflow.triggers]
          const deletedTrigger = triggers[index]

          if (!deletedTrigger) return state
          triggers.splice(index, 1)

          const deletedTriggerRealId = (deletedTrigger as { id?: string }).id
          const edges = deletedTriggerRealId
            ? state.edges.filter((edge) => edge.source !== deletedTriggerRealId && edge.target !== deletedTriggerRealId)
            : state.edges

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              triggers,
            },
            edges,
            isDirty: true,
          }
        })
      },

      updateTrigger: (index, trigger) => {
        set((state) => {
          if (!state.currentWorkflow?.triggers) return state

          const oldTrigger = state.currentWorkflow.triggers[index]
          // Only mark dirty if the trigger actually changed
          if (oldTrigger === trigger) return state

          const triggers = [...state.currentWorkflow.triggers]
          triggers[index] = trigger
          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              triggers,
            },
            isDirty: true,
          }
        })
      },

      addActivity: (activity) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities: [...state.currentWorkflow.workflow.activities, activity],
              },
            },
            isDirty: true,
          }
        })
        beginTemporalBatch(set)
      },

      duplicateActivity: (activityId) => {
        let newId: string | null = null

        set((state) => {
          if (!state.currentWorkflow) return state

          const original = findActivityById(state.currentWorkflow.workflow.activities, activityId)
          if (!original) return state

          const generatedId = generateActivityId()
          newId = generatedId

          const existingNames = new Set(
            state.currentWorkflow.workflow.activities
              .map((a) => a.name)
              .filter((name): name is string => Boolean(name?.trim()))
          )

          const baseName = `Copy of ${original.name ?? 'Node'}`
          let uniqueName = baseName
          if (existingNames.has(uniqueName)) {
            let suffix = 2
            while (existingNames.has(`${baseName}${suffix}`)) suffix++
            uniqueName = `${baseName}${suffix}`
          }

          // JSON round-trip for a safe deep-clone of plain data objects
          const clone = { ...(JSON.parse(JSON.stringify(original)) as Activity), id: generatedId, name: uniqueName }

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities: [...state.currentWorkflow.workflow.activities, clone],
              },
            },
            isDirty: true,
          }
        })

        beginTemporalBatch(set)
        return newId
      },

      removeActivity: (activityId) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          // v2: flat list, simply remove the activity
          const activities = removeActivityFromList(state.currentWorkflow.workflow.activities, activityId)

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities,
              },
            },
            isDirty: true,
          }
        })
      },

      updateActivity: (activityId, updates) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities: updateActivityInList(state.currentWorkflow.workflow.activities, activityId, updates),
              },
            },
            isDirty: true,
          }
        })
      },

      replaceActivity: (activityId, newActivity) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          // Remove outgoing edges whose handles are incompatible with the new
          // node type (e.g. condition true/false when replacing with switch, or
          // stale case_N ports when replacing one switch with another).
          // Bump workflowVersion so React Flow re-inits from this pruned store
          // state — otherwise useEdgeSynchronization can write stale RF edges back.
          const validHandles = getValidSourceHandles(newActivity.type)
          const edges = state.edges.filter(
            (edge) => edge.source !== activityId || edge.sourceHandle == null || validHandles.has(edge.sourceHandle)
          )

          return {
            edges,
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities: replaceActivityInList(state.currentWorkflow.workflow.activities, activityId, newActivity),
              },
            },
            workflowVersion: state.workflowVersion + 1,
            _preserveHistoryOnLayout: true,
            isDirty: true,
          }
        })
      },

      updateSwitchActivity: (nodeId, updatedActivity, portMapping) => {
        set((state) => {
          if (!state.currentWorkflow) return state
          return {
            edges: remapSwitchEdges(state.edges, nodeId, portMapping),
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities: replaceActivityInList(state.currentWorkflow.workflow.activities, nodeId, updatedActivity),
              },
            },
            workflowVersion: state.workflowVersion + 1,
            isDirty: true,
          }
        })
      },

      syncConvergeNodeBranches: () => {
        set((state) => {
          if (!state.currentWorkflow) return state

          const activities = [...state.currentWorkflow.workflow.activities]
          const convergeActivities = activities.filter((a) => a.type === ActivityTypeEnum.CONVERGE)

          if (convergeActivities.length === 0) return state

          // v2: no parallel containers — all nodes are flat.
          // Converge branches are determined by incoming edges.
          for (const convergeActivity of convergeActivities) {
            const incomingEdges = state.edges.filter((edge) => edge.target === convergeActivity.id)
            const branchIds = incomingEdges.map((edge) => edge.source)

            const convergeIndex = activities.findIndex((a) => a.id === convergeActivity.id)
            if (convergeIndex !== -1) {
              const existingParameters = convergeActivity.parameters ?? {}
              activities[convergeIndex] = {
                ...convergeActivity,
                parameters: {
                  ...existingParameters,
                  branches: branchIds,
                },
              } as Activity
            }
          }

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities,
              },
            },
            isDirty: true,
          }
        })
      },

      moveActivityBefore: (activityId: string, beforeActivityId: string) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          const activities = [...state.currentWorkflow.workflow.activities]

          // Find the activity to move and the target position
          const activityIndex = activities.findIndex((a) => a.id === activityId)
          const beforeIndex = activities.findIndex((a) => a.id === beforeActivityId)

          // If either not found, or if already in correct order, return unchanged
          if (activityIndex === -1 || beforeIndex === -1) return state
          if (activityIndex < beforeIndex) return state // Already before

          // Remove the activity from its current position
          const [activity] = activities.splice(activityIndex, 1)

          // Find the new position (might have changed after removal)
          const newBeforeIndex = activities.findIndex((a) => a.id === beforeActivityId)

          // Insert before the target
          activities.splice(newBeforeIndex, 0, activity)

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities,
              },
            },
            isDirty: true,
          }
        })
      },

      moveActivityAfter: (activityId: string, afterActivityId: string) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          const activities = [...state.currentWorkflow.workflow.activities]

          // Find the activity to move and the target position
          const activityIndex = activities.findIndex((a) => a.id === activityId)
          const afterIndex = activities.findIndex((a) => a.id === afterActivityId)

          // If either not found, or if already in correct order, return unchanged
          if (activityIndex === -1 || afterIndex === -1) return state
          if (activityIndex === afterIndex + 1) return state // Already right after

          // Remove the activity from its current position
          const [activity] = activities.splice(activityIndex, 1)

          // Find the new position (might have changed after removal)
          const newAfterIndex = activities.findIndex((a) => a.id === afterActivityId)

          // Insert after the target
          activities.splice(newAfterIndex + 1, 0, activity)

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities,
              },
            },
            isDirty: true,
          }
        })
      },

      reorderActivitiesFromEdges: () => {
        set((state) => {
          if (!state.currentWorkflow) return state

          const current = state.currentWorkflow.workflow.activities
          const reordered = reorderActivities(current, state.edges)
          if (reordered.every((act, i) => act === current[i])) return state

          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities: reordered,
              },
            },
            isDirty: true,
          }
        })
      },

      /**
       * Atomic batch operation to remove nodes and update edges simultaneously.
       * This prevents race conditions by updating all related state in a single transaction.
       *
       * Use this instead of calling removeActivity() and setEdges() separately to avoid:
       * - Ghost edges from initialEdges recomputation
       * - Race conditions between multiple async updates
       * - Synchronization issues
       */
      batchRemoveNodesAndEdges: ({ nodeIds, edges, triggerIndices = [] }) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          // Remove triggers immutably
          const triggerIndicesToRemove = new Set(triggerIndices)
          const triggers = state.currentWorkflow.triggers
            ? state.currentWorkflow.triggers.filter((_, index) => !triggerIndicesToRemove.has(index))
            : []

          // v2: flat list — just filter out the removed node IDs
          const nodeIdSet = new Set(nodeIds)
          const activities = state.currentWorkflow.workflow.activities.filter((a) => !nodeIdSet.has(a.id))

          // Build trigger index remapping using shared utility
          const originalTriggerCount = state.currentWorkflow.triggers?.length ?? 0
          const triggerIndexRemap = buildTriggerIndexRemappping(triggerIndicesToRemove, originalTriggerCount)

          // Remap trigger display IDs in edges using shared utility
          const updatedEdges = remapTriggerIdsInEdges(edges, triggerIndexRemap)

          // Update state atomically - all changes in one transaction
          return {
            currentWorkflow: {
              ...state.currentWorkflow,
              triggers: triggers.length > 0 ? triggers : undefined,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities,
              },
            },
            edges: updatedEdges,
            isDirty: true,
          }
        })
      },

      /**
       * Atomic batch operation to add activities and update edges simultaneously.
       * This prevents race conditions by updating all related state in a single transaction.
       *
       * Use this instead of calling addActivity() and setEdges() separately to avoid:
       * - Multiple re-renders triggering initialNodes recomputation
       * - Race conditions between multiple async updates
       * - useNodeUpdates running multiple times before positioning can complete
       */
      batchAddActivitiesAndEdges: ({ activities: newActivities, edges }) => {
        set((state) => {
          if (!state.currentWorkflow) return state

          const activities = [...state.currentWorkflow.workflow.activities, ...newActivities]

          // Update state atomically - all changes in one transaction
          return {
            ...state,
            currentWorkflow: {
              ...state.currentWorkflow,
              workflow: {
                ...state.currentWorkflow.workflow,
                activities,
              },
            },
            edges,
            isDirty: true,
          }
        })
        beginTemporalBatch(set)
      },

      clearNodePositions: () => {
        set(() => ({ nodePositions: {}, _positionsUserModified: false, isDirty: true }))
      },

      updateNodePositions: (positions, { markDirty = true, skipTracking = false } = {}) => {
        // skipTracking: absorb the position update without creating a new undo entry.
        // Used by useNodePositioning so the programmatic placement of a newly added
        // node is folded into the already-committed "add node" temporal entry rather
        // than spawning a separate position-only entry.
        const current = get().nodePositions
        const allSame = Object.entries(positions).every(([id, pos]) => {
          const cur = current[id]
          return cur?.x === pos.x && cur?.y === pos.y
        })
        if (allSame) return

        const batchPending = useWorkflowStore.getState()._temporalBatchPending
        const shouldPause = skipTracking && !batchPending
        if (shouldPause) {
          useWorkflowStore.temporal.getState().pause()
        }
        set((state) => ({
          nodePositions: { ...state.nodePositions, ...positions },
          ...(markDirty ? { isDirty: true, _positionsUserModified: true } : {}),
        }))
        if (shouldPause) {
          useWorkflowStore.temporal.getState().resume()
        }
      },
    }),
    {
      limit: HISTORY_LIMIT,
      partialize: (state) => ({
        currentWorkflow: state.currentWorkflow,
        edges: state.edges,
        nodePositions: state.nodePositions,
      }),
      equality: (pastState, currentState) =>
        workflowEqual(pastState.currentWorkflow, currentState.currentWorkflow) &&
        edgesEqual(pastState.edges, currentState.edges) &&
        pastState.nodePositions === currentState.nodePositions,
    }
  )
)

export { edgesEqual, workflowEqual } from './workflowStoreEquality'
export type {
  WorkflowStore,
  WorkflowDefinition,
  Trigger,
  Activity,
  ActivityWithMetadata,
  ActivityMetadata,
} from './workflowStoreTypes'
export { getActivityMetadata } from './workflowStoreTypes'
export * from './workflowStoreSelectors'

// ============================================================================
// Factory Functions - Re-exported from workflowFactories.ts
// ============================================================================
// These functions are maintained in a separate file for better organization.
// They are re-exported here for backward compatibility.
// ============================================================================
export {
  createManualTrigger,
  createScheduledTrigger,
  createEventTrigger,
  createWebhookTrigger,
  createEdaTrigger,
  createScriptActivity,
  createApiActivity,
  createAgenticActivity,
  createConditionActivity,
  createLoopActivity,
  createConvergeActivity,
  createSwitchActivity,
  createAAPJobTemplateActivity,
  createAAPWorkflowTemplateActivity,
  createGenericActivity,
  createApprovalActivity,
  createWaitActivity,
} from './workflowFactories'
export type {
  CreateApiActivityOptions,
  CreateAgenticActivityOptions,
  CreateApprovalActivityOptions,
} from './workflowFactories'
