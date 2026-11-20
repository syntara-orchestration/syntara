import { useQueries } from '@tanstack/react-query'
import { useMemo } from 'react'

import { formatStepTypeWriteDenial } from '../../utils/nodeKindDenials'
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

export type BlockedStepType = { kind: string; label: string }

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
  return permissions.blockedStepTypes.length
    ? formatStepTypeWriteDenial(permissions.blockedStepTypes)
    : 'Step-type permission is required.'
}

function getStepTypeDisplayName(kind: string): string {
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
  return [...types].sort((a, b) => a.localeCompare(b))
}

export function useStepTypePermissions(
  stepTypes: string[] | null | undefined,
  resourceProject: string | undefined,
  options: { enabled?: boolean; retryContext?: () => Promise<unknown> } = {}
): StepTypePermissions {
  const enabled = options.enabled !== false
  const hasContext = stepTypes !== null && stepTypes !== undefined
  const kinds = useMemo(() => [...new Set(stepTypes ?? [])].sort((a, b) => a.localeCompare(b)), [stepTypes])
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

  const canCheck = enabled && hasContext && Boolean(resourceProject)
  const isChecking = canCheck && queries.some((query) => query.isPending || query.isFetching)
  // A query has a usable decision once it settled without an error and returned
  // an explicit allow or deny. openapi-fetch sets `error` on any non-ok response,
  // so a successful query with no error always carries the decision payload.
  const hasDecision = (query: (typeof queries)[number]) =>
    !query.isError && query.data?.error === undefined && typeof query.data?.data?.allowed === 'boolean'
  const isError = enabled && (!canCheck || (!isChecking && queries.some((query) => !hasDecision(query))))
  const blockedStepTypes = enabled
    ? kinds.flatMap((kind, index) =>
        queries[index].data?.data?.allowed === false ? [{ kind, label: getStepTypeDisplayName(kind) }] : []
      )
    : []
  const retry = async () => {
    if (!hasContext || !resourceProject) {
      await options.retryContext?.()
      return
    }
    await Promise.all(queries.map((query) => query.refetch()))
  }

  return {
    canAuthor: !enabled || (canCheck && !isChecking && !isError && blockedStepTypes.length === 0),
    blockedStepTypes,
    isChecking,
    isError,
    retry,
  }
}
