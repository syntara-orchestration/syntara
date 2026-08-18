import type { AAPAPI } from '@syntara/contracts'
import { useCallback, useMemo, useState } from 'react'

import { aapClient } from '../client'
import { detachPromise } from '../utils/detachPromise'
import { sanitizeSearchInput } from '../utils/searchSanitization'

export type AAPOrganization = AAPAPI.components['schemas']['AAPOrganization']
export type AAPJobTemplate = AAPAPI.components['schemas']['AAPJobTemplate']
export type AAPJobTemplateDetail = AAPAPI.components['schemas']['AAPJobTemplateDetail']
export type AAPInventory = AAPAPI.components['schemas']['AAPInventory']
export type AAPExecutionEnvironment = AAPAPI.components['schemas']['AAPExecutionEnvironment']
export type AAPCredential = AAPAPI.components['schemas']['AAPCredential']
export type AAPInstanceGroup = AAPAPI.components['schemas']['AAPInstanceGroup']
export type AAPLabel = AAPAPI.components['schemas']['AAPLabel']

// Workflow template types
export type AAPWorkflowTemplate = AAPAPI.components['schemas']['AAPWorkflowJobTemplate']
export type AAPWorkflowTemplateDetail = AAPAPI.components['schemas']['AAPWorkflowJobTemplateDetail']

type AAPSearchState = {
  selectedOrg: string
  selectedTemplateId: number | undefined
  orgSearch: string
  templateSearch: string
  inventorySearch: string
  execEnvSearch: string
  credentialSearch: string
  instanceGroupSearch: string
  labelSearch: string
}

const INITIAL_STATE: AAPSearchState = {
  selectedOrg: '',
  selectedTemplateId: undefined,
  orgSearch: '',
  templateSearch: '',
  inventorySearch: '',
  execEnvSearch: '',
  credentialSearch: '',
  instanceGroupSearch: '',
  labelSearch: '',
}

export type AAPBrowserTemplateType = 'job' | 'workflow'

export type AAPBrowserInitialState = {
  readonly organization?: string
  readonly templateId?: number
  /** @deprecated Use templateId instead */
  readonly jobTemplateId?: number
}

/** AAP Controller defaults to page_size=25; request more to populate full dropdowns */
const AAP_DROPDOWN_PAGE_SIZE = 200

function getFirstError(...errors: (Error | Record<string, unknown> | null)[]): Error | null {
  for (const err of errors) {
    if (err) return err instanceof Error ? err : new Error(JSON.stringify(err))
  }
  return null
}

/** Extract results array from a query, sorted alphabetically by name. */
function resultsOf<T extends { name: string }>(query: { data?: { results?: T[] } }): T[] {
  return [...(query.data?.results ?? [])].sort((a, b) => a.name.localeCompare(b.name))
}

/** Build common query params for AAP resource searches */
function buildSearchParams(
  search: string,
  credentialId: string | undefined,
  organization?: string,
  integrationId?: string
) {
  return {
    search: search ? sanitizeSearchInput(search) : undefined,
    page_size: AAP_DROPDOWN_PAGE_SIZE,
    credential_id: credentialId || undefined,
    integration_id: integrationId || undefined,
    organization: organization || undefined,
  }
}

function useAAPQueries(
  state: AAPSearchState,
  isActive: boolean,
  credentialId: string | undefined,
  templateType: AAPBrowserTemplateType,
  integrationId?: string
) {
  const orgsQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/organizations',
    { params: { query: buildSearchParams(state.orgSearch, credentialId, undefined, integrationId) } },
    { enabled: isActive }
  )

  // Job templates query
  const jobTemplatesQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/job_templates',
    { params: { query: buildSearchParams(state.templateSearch, credentialId, state.selectedOrg, integrationId) } },
    { enabled: isActive && templateType === 'job' }
  )

  const jobTemplateDetailQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/job_templates/{job_template_id}',
    {
      params: {
        path: { job_template_id: state.selectedTemplateId ?? 0 },
        query: { credential_id: credentialId || undefined, integration_id: integrationId || undefined },
      },
    },
    { enabled: isActive && templateType === 'job' && state.selectedTemplateId != null }
  )

  // Workflow templates query
  const workflowTemplatesQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/workflow_job_templates',
    { params: { query: buildSearchParams(state.templateSearch, credentialId, state.selectedOrg, integrationId) } },
    { enabled: isActive && templateType === 'workflow' }
  )

  const workflowTemplateDetailQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/workflow_job_templates/{workflow_job_template_id}',
    {
      params: {
        path: { workflow_job_template_id: state.selectedTemplateId ?? 0 },
        query: { credential_id: credentialId || undefined, integration_id: integrationId || undefined },
      },
    },
    { enabled: isActive && templateType === 'workflow' && state.selectedTemplateId != null }
  )

  const inventoriesQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/inventories',
    { params: { query: buildSearchParams(state.inventorySearch, credentialId, state.selectedOrg, integrationId) } },
    { enabled: isActive }
  )

  const execEnvsQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/execution_environments',
    { params: { query: buildSearchParams(state.execEnvSearch, credentialId, state.selectedOrg, integrationId) } },
    { enabled: isActive && templateType === 'job' } // Only needed for job templates
  )

  const credentialsQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/credentials',
    { params: { query: buildSearchParams(state.credentialSearch, credentialId, undefined, integrationId) } },
    { enabled: isActive && templateType === 'job' } // Only needed for job templates
  )

  const instanceGroupsQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/instance_groups',
    { params: { query: buildSearchParams(state.instanceGroupSearch, credentialId, undefined, integrationId) } },
    { enabled: isActive && templateType === 'job' } // Only needed for job templates
  )

  const labelsQuery = aapClient.useQuery(
    'get',
    '/proxies/aap/labels',
    { params: { query: buildSearchParams(state.labelSearch, credentialId, state.selectedOrg, integrationId) } },
    { enabled: isActive }
  )

  return {
    orgsQuery,
    jobTemplatesQuery,
    jobTemplateDetailQuery,
    workflowTemplatesQuery,
    workflowTemplateDetailQuery,
    inventoriesQuery,
    execEnvsQuery,
    credentialsQuery,
    instanceGroupsQuery,
    labelsQuery,
  }
}

function useAAPActions(setState: React.Dispatch<React.SetStateAction<AAPSearchState>>) {
  const selectOrganization = useCallback(
    (orgName: string) => {
      setState((prev) => ({
        ...prev,
        selectedOrg: orgName,
        selectedTemplateId: undefined,
        templateSearch: '',
        inventorySearch: '',
        execEnvSearch: '',
        labelSearch: '',
      }))
    },
    [setState]
  )

  const selectTemplate = useCallback(
    (templateId: number | undefined) => {
      setState((prev) => ({ ...prev, selectedTemplateId: templateId }))
    },
    [setState]
  )

  // Keep backward compatibility alias
  const selectJobTemplate = selectTemplate

  const resetAll = useCallback(() => {
    setState(INITIAL_STATE)
  }, [setState])

  const searchOrganizations = useCallback((s: string) => setState((prev) => ({ ...prev, orgSearch: s })), [setState])
  const searchTemplates = useCallback((s: string) => setState((prev) => ({ ...prev, templateSearch: s })), [setState])
  // Keep backward compatibility alias
  const searchJobTemplates = searchTemplates

  const searchInventories = useCallback(
    (s: string) => setState((prev) => ({ ...prev, inventorySearch: s })),
    [setState]
  )
  const searchExecutionEnvironments = useCallback(
    (s: string) => setState((prev) => ({ ...prev, execEnvSearch: s })),
    [setState]
  )
  const searchCredentials = useCallback(
    (s: string) => setState((prev) => ({ ...prev, credentialSearch: s })),
    [setState]
  )
  const searchInstanceGroups = useCallback(
    (s: string) => setState((prev) => ({ ...prev, instanceGroupSearch: s })),
    [setState]
  )
  const searchLabels = useCallback((s: string) => setState((prev) => ({ ...prev, labelSearch: s })), [setState])

  return {
    selectOrganization,
    selectTemplate,
    selectJobTemplate, // backward compatibility
    resetAll,
    searchOrganizations,
    searchTemplates,
    searchJobTemplates, // backward compatibility
    searchInventories,
    searchExecutionEnvironments,
    searchCredentials,
    searchInstanceGroups,
    searchLabels,
  }
}

function useAAPBrowserResults(
  queries: ReturnType<typeof useAAPQueries>,
  isActive: boolean,
  selectedTemplateId: number | undefined,
  templateType: AAPBrowserTemplateType
) {
  return useMemo(
    // eslint-disable-next-line complexity, sonarjs/cognitive-complexity
    () => ({
      organizations: resultsOf(queries.orgsQuery),
      jobTemplates: templateType === 'job' ? resultsOf(queries.jobTemplatesQuery) : [],
      workflowTemplates: templateType === 'workflow' ? resultsOf(queries.workflowTemplatesQuery) : [],
      templates:
        templateType === 'job' ? resultsOf(queries.jobTemplatesQuery) : resultsOf(queries.workflowTemplatesQuery),
      inventories: resultsOf(queries.inventoriesQuery),
      executionEnvironments: resultsOf(queries.execEnvsQuery),
      credentials: resultsOf(queries.credentialsQuery),
      instanceGroups: resultsOf(queries.instanceGroupsQuery),
      labels: resultsOf(queries.labelsQuery),
      jobTemplateDetail: templateType === 'job' ? queries.jobTemplateDetailQuery.data : undefined,
      workflowTemplateDetail: templateType === 'workflow' ? queries.workflowTemplateDetailQuery.data : undefined,
      templateDetail:
        templateType === 'job' ? queries.jobTemplateDetailQuery.data : queries.workflowTemplateDetailQuery.data,
      loadingOrgs: queries.orgsQuery.isPending && isActive,
      loadingTemplates:
        templateType === 'job'
          ? queries.jobTemplatesQuery.isPending && isActive
          : queries.workflowTemplatesQuery.isPending && isActive,
      loadingInventories: queries.inventoriesQuery.isPending && isActive,
      loadingExecutionEnvironments: queries.execEnvsQuery.isPending && isActive,
      loadingCredentials: queries.credentialsQuery.isPending && isActive,
      loadingInstanceGroups: queries.instanceGroupsQuery.isPending && isActive,
      loadingLabels: queries.labelsQuery.isPending && isActive,
      loadingTemplateDetail:
        templateType === 'job'
          ? queries.jobTemplateDetailQuery.isPending && selectedTemplateId != null
          : queries.workflowTemplateDetailQuery.isPending && selectedTemplateId != null,
      error: getFirstError(
        queries.orgsQuery.error,
        templateType === 'job' ? queries.jobTemplatesQuery.error : queries.workflowTemplatesQuery.error,
        queries.inventoriesQuery.error,
        templateType === 'job' ? queries.jobTemplateDetailQuery.error : queries.workflowTemplateDetailQuery.error,
        queries.execEnvsQuery.error,
        queries.credentialsQuery.error,
        queries.instanceGroupsQuery.error,
        queries.labelsQuery.error
      ),
    }),
    [
      queries.orgsQuery,
      queries.jobTemplatesQuery,
      queries.workflowTemplatesQuery,
      queries.inventoriesQuery,
      queries.execEnvsQuery,
      queries.credentialsQuery,
      queries.instanceGroupsQuery,
      queries.labelsQuery,
      queries.jobTemplateDetailQuery,
      queries.workflowTemplateDetailQuery,
      isActive,
      selectedTemplateId,
      templateType,
    ]
  )
}

/**
 * Hook to browse AAP resources (organizations, job/workflow templates, inventories,
 * execution environments, credentials, instance groups) via the Syntara backend proxy.
 *
 * @param credentialId - AAP credential ID to use for authentication
 * @param initialState - Initial organization and template selection
 * @param templateType - 'job' for job templates (default) or 'workflow' for workflow templates
 *
 * When credentialId is provided, the hook fetches organizations
 * on mount. When an organization is selected, it re-fetches
 * resources filtered by that org.
 */
export function useAAPBrowser(
  credentialId: string | undefined,
  initialState?: AAPBrowserInitialState,
  templateType: AAPBrowserTemplateType = 'job',
  integrationId?: string
) {
  const [state, setState] = useState<AAPSearchState>(() => ({
    ...INITIAL_STATE,
    selectedOrg: initialState?.organization ?? '',
    selectedTemplateId: initialState?.templateId ?? initialState?.jobTemplateId,
  }))
  const isActive = credentialId !== undefined || integrationId !== undefined

  const queries = useAAPQueries(state, isActive, credentialId, templateType, integrationId)
  const actions = useAAPActions(setState)

  const retryAll = useCallback(() => {
    const allQueries = [
      queries.orgsQuery,
      templateType === 'job' ? queries.jobTemplatesQuery : queries.workflowTemplatesQuery,
      queries.inventoriesQuery,
      templateType === 'job' ? queries.jobTemplateDetailQuery : queries.workflowTemplateDetailQuery,
      queries.execEnvsQuery,
      queries.credentialsQuery,
      queries.instanceGroupsQuery,
      queries.labelsQuery,
    ]
    detachPromise(Promise.all(allQueries.map((q) => q.refetch())))
  }, [
    queries.orgsQuery,
    queries.jobTemplatesQuery,
    queries.workflowTemplatesQuery,
    queries.inventoriesQuery,
    queries.jobTemplateDetailQuery,
    queries.workflowTemplateDetailQuery,
    queries.execEnvsQuery,
    queries.credentialsQuery,
    queries.instanceGroupsQuery,
    queries.labelsQuery,
    templateType,
  ])

  return {
    ...useAAPBrowserResults(queries, isActive, state.selectedTemplateId, templateType),
    selectedOrg: state.selectedOrg,
    ...actions,
    retryAll,
  }
}
