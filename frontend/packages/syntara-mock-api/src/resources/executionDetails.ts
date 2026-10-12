import type { Execution, ExecutionsAPI } from '@syntara/contracts'

import { activityExecutions, type ActivityExecutionMockSeed } from './activityExecutions'
import { executions } from './executions'
import { workflows } from './workflows'

type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type WorkflowNode = ExecutionsAPI.components['schemas']['WorkflowDefinition']['nodes'][number]

/** GET /executions/{id} detail built from mock stores (may omit fields handlers enrich at list time). */
type ExecutionDetailResponse = Omit<
  Execution,
  'workflow_version_id' | 'project_id' | 'temporal_workflow_id' | 'error_details' | 'workflow_definition'
> &
  Partial<Pick<Execution, 'workflow_version_id' | 'temporal_workflow_id' | 'error_details'>> & {
    project_id?: string | null
    /** Full YAML definitions or node-only overrides for E2E scenarios. */
    workflow_definition?: { nodes: WorkflowNode[] } | Record<string, unknown> | null
  }

const collectInputFormParameters = {
  form_definition: {
    fields: [{ value_name: 'reason', type: 'text' as const, label: 'Reason', required: true }],
  },
} satisfies Extract<WorkflowNode, { type: 'form_prompt' }>['parameters']

const continueDefaultsScriptParameters = {
  language: 'python' as const,
  code: '# continue with defaults',
} satisfies Extract<WorkflowNode, { type: 'script' }>['parameters']

function toActivityData(activity: ActivityExecutionMockSeed): ActivityData {
  return {
    activity_id: activity.activity_name ?? activity.id ?? '',
    status: activity.status ?? 'pending',
    error_details: activity.error_details,
    output_data: activity.output_data,
    started_at: activity.started_at,
    completed_at: activity.completed_at,
  }
}

function collectInputNode(settings?: { timeout: number }): WorkflowNode {
  return {
    id: 'collect_input',
    type: 'form_prompt',
    name: 'Collect operator input',
    parameters: collectInputFormParameters,
    ...(settings ? { settings } : {}),
  }
}

function continueDefaultsNode(): WorkflowNode {
  return {
    id: 'continue_with_defaults',
    type: 'script',
    name: 'Continue with defaults step',
    parameters: continueDefaultsScriptParameters,
  }
}

/** Build full execution detail from live stores (matches GET /executions/{id}?include=...). */
export function getExecutionDetail(executionId: string): ExecutionDetailResponse | undefined {
  const execution = executions.find((item) => item.id === executionId)
  if (!execution) return undefined

  const workflow = workflows.find((item) => item.id === execution.workflow_id)
  const base: ExecutionDetailResponse = {
    ...execution,
    activities: (activityExecutions[execution.id] ?? []).map(toActivityData),
    workflow_definition: workflow?.version?.workflow_definition as ExecutionDetailResponse['workflow_definition'],
  }

  if (execution.id === 'exec-form-prompt') {
    return {
      ...base,
      workflow_definition: { nodes: [collectInputNode({ timeout: 1 })] },
    }
  }

  if (execution.id === 'exec-form-prompt-timeout-fail') {
    return {
      ...base,
      workflow_definition: { nodes: [collectInputNode()] },
    }
  }

  if (execution.id === 'exec-form-prompt-fallback-continue') {
    return {
      ...base,
      workflow_definition: { nodes: [collectInputNode(), continueDefaultsNode()] },
    }
  }

  return base
}
