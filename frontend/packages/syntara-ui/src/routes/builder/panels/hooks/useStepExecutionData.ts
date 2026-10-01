import type { ActivityExecution } from '@syntara/contracts'
import { useMemo } from 'react'

import { executionsClient } from '../../../../client'

import { useUpstreamSteps } from './useUpstreamSteps'

type StepExecutionData = {
  inputData: Record<string, Record<string, unknown>> | null
  outputData: Record<string, unknown> | null
  isLoading: boolean
}

/**
 * Type guard that narrows an ActivityExecution's output_data from the codegen
 * `Record<string, never>` to a usable record type at runtime.
 */
function hasOutputData(
  activity: ActivityExecution
): activity is ActivityExecution & { output_data: Record<string, unknown> } {
  return activity.output_data !== null && activity.output_data !== undefined && typeof activity.output_data === 'object'
}

/**
 * Fetches activity execution data for a specific node.
 *
 * When an explicit `executionId` is provided, fetches activities for that execution.
 * When only `workflowId` is provided, fetches the latest completed execution for
 * the workflow and uses its activities — so data shows in edit mode after a run.
 *
 * - `outputData`: the output_data from the activity whose activity_name matches `nodeId`
 * - `inputData`: for each upstream node, keyed by node id, the upstream activity's output_data
 *   (upstream output = this node's input)
 */
export function useStepExecutionData(
  nodeId: string,
  executionId?: string | null,
  workflowId?: string | null
): StepExecutionData {
  const upstreamNodes = useUpstreamSteps(nodeId)

  // If no explicit executionId, fetch the latest execution for this workflow
  const latestExecQuery = executionsClient.useQuery(
    'get',
    '/executions',
    {
      params: {
        query: {
          workflow_id: workflowId ?? '',
          sort: '-created_at',
          limit: 1,
        },
      },
    },
    { enabled: !executionId && !!workflowId }
  )

  const latestExecutionId = useMemo(() => {
    if (executionId) return executionId
    const resources = latestExecQuery.data?.resources
    if (resources && resources.length > 0) {
      const latest = resources[0]
      if (latest.status === 'completed' || latest.status === 'failed') {
        return latest.id
      }
    }
    return null
  }, [executionId, latestExecQuery.data])

  // Fetch activities for the resolved execution
  const activitiesQuery = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}/activities',
    {
      params: { path: { execution_id: latestExecutionId ?? '' } },
    },
    { enabled: !!latestExecutionId }
  )

  const isLoading = latestExecQuery.isLoading || activitiesQuery.isLoading

  return useMemo(() => {
    if (!latestExecutionId || !activitiesQuery.data) {
      return { inputData: null, outputData: null, isLoading }
    }

    const activities = activitiesQuery.data.resources ?? []

    // Current node's output
    const currentActivity = activities.find((a) => a.activity_name === nodeId)
    const outputData = currentActivity && hasOutputData(currentActivity) ? currentActivity.output_data : null

    // Upstream nodes' outputs = this node's input
    const inputData: Record<string, Record<string, unknown>> = {}
    for (const upstream of upstreamNodes) {
      const upstreamActivity = activities.find((a) => a.activity_name === upstream.id)
      if (upstreamActivity && hasOutputData(upstreamActivity)) {
        inputData[upstream.id] = upstreamActivity.output_data
      }
    }

    const hasInput = Object.keys(inputData).length > 0

    return {
      inputData: hasInput ? inputData : null,
      outputData,
      isLoading,
    }
  }, [latestExecutionId, activitiesQuery.data, isLoading, nodeId, upstreamNodes])
}
