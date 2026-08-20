import type { SettingsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { settingsFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

type RuntimeSettingRead = SettingsAPI.components['schemas']['RuntimeSettingRead']

export type WorkflowEngineDefaults = {
  continueOnFailure: boolean | null
  timeoutSeconds: {
    script: number | null
    agentic: number | null
    aap: number | null
    approval: number | null
    http_request: number | null
  }
  convergeWaitDuration: number | null
  retry: {
    maxRetries: number | null
    initialInterval: number | null
    maxInterval: number | null
    backoffCoefficient: number | null
  }
  maxLoopIterations: number | null
}

/** Query key for workflow engine defaults. Invalidate after admin settings change. */
export const WORKFLOW_ENGINE_DEFAULTS_QUERY_KEY = ['workflow-engine-defaults'] as const

async function fetchWorkflowEngineDefaults(): Promise<WorkflowEngineDefaults> {
  const allSettings = await fetchAllPages<RuntimeSettingRead>((cursor) =>
    settingsFetchClient.GET('/settings', {
      params: { query: { category: 'workflow_execution', limit: MAX_PAGE_SIZE, cursor } },
    })
  )

  const map: Record<string, unknown> = {}
  for (const s of allSettings) {
    map[s.key] = s.effective_value
  }

  const num = (key: string): number | null => {
    const v = map[key]
    return typeof v === 'number' ? v : null
  }
  const bool = (key: string): boolean | null => {
    const v = map[key]
    return typeof v === 'boolean' ? v : null
  }

  return {
    continueOnFailure: bool('workflow_engine.continue_on_failure'),
    timeoutSeconds: {
      script: num('workflow_engine.script_timeout_seconds'),
      agentic: num('workflow_engine.agentic_timeout_seconds'),
      aap: num('workflow_engine.aap_timeout_seconds'),
      approval: num('workflow_engine.approval_decision_window_seconds'),
      http_request: num('workflow_engine.http_request_timeout_seconds'),
    },
    convergeWaitDuration: num('workflow_engine.converge_wait_duration_seconds'),
    retry: {
      maxRetries: num('workflow_engine.retry_max_retries'),
      initialInterval: num('workflow_engine.retry_initial_interval'),
      maxInterval: num('workflow_engine.retry_max_interval'),
      backoffCoefficient: num('workflow_engine.retry_backoff_coefficient'),
    },
    maxLoopIterations: num('workflow_engine.max_loop_iterations'),
  }
}

export function useWorkflowEngineDefaults() {
  const { data, isPending } = useQuery({
    queryKey: WORKFLOW_ENGINE_DEFAULTS_QUERY_KEY,
    queryFn: fetchWorkflowEngineDefaults,
    // Keep defaults in sync with admin settings (fallback decision, timeouts).
    staleTime: 0,
  })
  return { defaults: data ?? null, isLoading: isPending }
}

export type TimeoutNodeType = keyof WorkflowEngineDefaults['timeoutSeconds']
