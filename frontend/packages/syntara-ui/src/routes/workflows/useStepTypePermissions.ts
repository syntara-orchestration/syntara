import { useQueries } from '@tanstack/react-query'
import { useMemo } from 'react'

import { accessFetchClient } from '../access/accessClient'

const STEP_TYPE_LABELS: Record<string, string> = {
  manual_trigger: 'Manual trigger',
  scheduled_trigger: 'Schedule trigger',
  webhook_trigger: 'Webhook trigger',
  eda_trigger: 'Event-Driven Ansible trigger',
  condition: 'Conditional',
  converge: 'Converge',
  loop: 'Loop',
  switch: 'Switch',
  wait: 'Wait',
  aap_job_template: 'AAP Job Template',
  aap_workflow_job_template: 'AAP Workflow Template',
  agentic: 'Task Agent',
  approval: 'Approval',
  http_request: 'REST API',
  script: 'Script',
}

export type BlockedStepType = { kind: string; label: string; description?: string }

export type StepTypePermissions = {
  canAuthor: boolean
  blockedStepTypes: BlockedStepType[]
  isChecking: boolean
  isError: boolean
  retry: () => Promise<void>
}

export function getStepTypePermissionMessage(
  permissions: Pick<StepTypePermissions, 'blockedStepTypes' | 'isChecking' | 'isError'>
): string {
  if (permissions.isError) return 'Unable to check step-type permissions. Retry the check.'
  if (permissions.isChecking) return 'Checking step-type permissions.'
  const reasons = permissions.blockedStepTypes.map(
    (stepType) => stepType.description ?? `${stepType.label} (write denied).`
  )
  return reasons.length ? reasons.join(' ') : 'Step-type permission is required.'
}

export function getStepTypeDisplayName(kind: string): string {
  return STEP_TYPE_LABELS[kind] ?? kind.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function getStepTypesFromDefinition(definition: Record<string, unknown> | undefined): string[] | undefined {
  if (!definition || typeof definition !== 'object') return undefined
  const types = new Set<string>()
  for (const collection of ['nodes', 'triggers']) {
    const items = definition[collection]
    if (!Array.isArray(items)) continue
    for (const item of items) {
      if (!isRecord(item)) continue
      const type = item.type
      if (typeof type === 'string') types.add(type)
    }
  }
  return [...types].sort()
}

export function useStepTypePermissions(
  stepTypes: string[] | null | undefined,
  resourceProject: string | undefined,
  options: { enabled?: boolean; retryContext?: () => Promise<unknown> } = {}
): StepTypePermissions {
  const enabled = options.enabled !== false
  const hasContext = stepTypes !== null && stepTypes !== undefined
  const kinds = useMemo(() => [...new Set(stepTypes ?? [])].sort(), [stepTypes])
  const queries = useQueries({
    queries: kinds.map((kind) => {
      const body = {
        action: 'write',
        resource_type: 'step_type',
        resource_labels: { kind },
        ...(resourceProject ? { resource_project: resourceProject } : {}),
      }
      return {
        queryKey: ['authz', 'can_i', body] as const,
        queryFn: () => accessFetchClient.POST('/authz/can_i', { body }),
        enabled: enabled && hasContext && Boolean(resourceProject),
        staleTime: 0,
        retry: false,
      }
    }),
  })

  const isChecking = enabled && queries.some((query) => query.isPending || query.isFetching)
  const isError = enabled && (!hasContext || !resourceProject || queries.some((query) => query.isError))
  const blockedStepTypes = kinds
    .filter((_, index) => queries[index]?.data?.data?.allowed !== true)
    .map((kind) => {
      const decision = queries[kinds.indexOf(kind)]?.data?.data
      const label = getStepTypeDisplayName(kind)
      const project = decision?.denied_project || resourceProject
      let description = `${label} (write permission denied).`
      if (decision?.denial_reason === 'no_matching_allow' || (decision && !decision.denied && !decision.denied_by)) {
        description = `No policy grants write permission for ${label} in project ${project}.`
      } else if (decision?.denied_by) {
        const scope =
          decision.denied_scope === 'any' ? 'all projects' : `${decision.denied_scope || 'project'} ${project}`
        description = `${label} (${decision.denied_by}, ${scope}).`
      }
      return { kind, label, description }
    })
  const retry = async () => {
    if (!hasContext || !resourceProject) {
      await options.retryContext?.()
      return
    }
    await Promise.all(queries.map((query) => query.refetch()))
  }

  return {
    canAuthor:
      !enabled || (hasContext && Boolean(resourceProject) && !isChecking && !isError && blockedStepTypes.length === 0),
    blockedStepTypes,
    isChecking,
    isError,
    retry,
  }
}
