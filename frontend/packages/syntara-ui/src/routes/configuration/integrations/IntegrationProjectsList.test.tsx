import type { IntegrationsAPI, Tool } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient, integrationsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'

import { IntegrationDetail } from './IntegrationDetail'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  credentialsClient: {
    useQuery: vi.fn(),
  },
}))

vi.mock('./useAllIntegrationTools', () => ({
  useAllIntegrationTools: () => ({
    tools: [] as Tool[],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('./useItemSelection', () => ({
  useItemSelection: () => ({
    enabledIds: new Set<string>(),
    enabledCount: 0,
    allSelected: false,
    isDirty: false,
    handleSelectAll: vi.fn(),
    handleSelectItem: vi.fn(),
    resetToServer: vi.fn(),
  }),
}))

vi.mock('./useIntegrationModelsState', () => ({
  useIntegrationModelsState: () => ({
    models: [],
    isLoading: false,
    error: null,
    refetchModels: vi.fn().mockResolvedValue(undefined),
    enabledModelIds: new Set<string>(),
    enabledCount: 0,
    allSelected: false,
    isDirty: false,
    isSaving: false,
    handleSave: vi.fn(),
    handleSelectAll: vi.fn(),
    defaultModelId: null,
    handleSelectWithDefaultClear: vi.fn(),
    handleSetDefault: vi.fn(),
    handleRemoveDefault: vi.fn(),
    resetSelectionToServer: vi.fn(),
    resetDefault: vi.fn(),
  }),
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
      <a href={String(to)} {...rest}>
        {children}
      </a>
    ),
    useNavigate: () => vi.fn(),
    useParams: vi.fn(() => ({ integrationId: 'int-1' })),
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const state = { location: { pathname: '/configuration/integrations/int-1', searchStr: '' } }
      return opts?.select ? opts.select(state) : state
    },
  }
})

vi.mock('./IntegrationModelsTab', () => ({
  IntegrationModelsTab: () => <div data-testid="models-tab-content">Models tab content</div>,
}))

vi.mock('./IntegrationResourcesTab', () => ({
  IntegrationResourcesTab: () => <div data-testid="resources-tab-content">Resources tab content</div>,
}))

vi.mock('../../../hooks/useUrlTab', () => ({
  useUrlTab: (): [string, (tab: string) => void] => ['details', vi.fn()],
}))

vi.mock('../../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({
    requestNavigation: vi.fn(),
    registerSaveHandler: vi.fn(),
    unregisterSaveHandler: vi.fn() as () => void,
    registerDirtyCheck: vi.fn(() => () => {}),
  }),
}))

vi.mock('./useIntegrationPermissions', () => ({
  useIntegrationPermissions: () => ({
    canCreate: true,
    canUpdate: true,
    canDelete: true,
    isLoading: false,
    tooltips: {
      create: 'No create permission',
      update: 'No update permission',
      enable: 'No enable permission',
      validate: 'No validate permission',
      delete: 'No delete permission',
    },
  }),
}))

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const baseIntegration: IntegrationRead = {
  id: 'int-1',
  name: 'Test Integration',
  description: 'A test integration',
  integration_type: 'mcp_server',
  enabled: true,
  validation_status: 'available',
  scope: 'global',
  configuration: {
    integration_type: 'mcp_server',
    base_url: 'https://mcp.example.com',
  },
  management_credential_id: null,
  last_validated_at: '2026-01-01T00:00:00Z',
  validation_error: null,
  refresh_status: 'available',
  last_refreshed_at: '2026-01-01T00:00:00Z',
  refresh_error: null,
  enabled_tool_count: 0,
  total_tool_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1' },
  labels: {},
}

const mockProjectAssignments = {
  resources: [
    { project_id: 'proj-1', project_name: 'Alpha Project', integration_id: 'int-1' },
    { project_id: 'proj-2', project_name: 'Beta Project', integration_id: 'int-1' },
  ],
}

function setupMocks(overrides?: {
  integration?: Partial<IntegrationRead>
  projectsData?: unknown
  projectsPending?: boolean
}) {
  const integration = overrides?.integration ? { ...baseIntegration, ...overrides.integration } : baseIntegration

  vi.mocked(integrationsClient.useQuery).mockImplementation((_method: string, path: string) => {
    if (path === '/integrations/{integration_id}/projects') {
      return {
        data: overrides?.projectsPending ? undefined : (overrides?.projectsData ?? mockProjectAssignments),
        isPending: overrides?.projectsPending ?? false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never
    }
    return {
      data: integration,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn().mockResolvedValue({ data: integration }),
    } as never
  })

  vi.mocked(credentialsClient.useQuery).mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    error: null,
  } as never)

  vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
    if (path === '/integrations/{integration_id}/tools/bulk_update') {
      return {
        mutateAsync: vi.fn().mockResolvedValue({}),
        mutate: vi.fn(),
        isPending: false,
        isIdle: true,
        isSuccess: false,
        isError: false,
        error: null,
        data: null,
        reset: vi.fn(),
        failureCount: 0,
        failureReason: null,
        context: undefined,
        submittedAt: 0,
        variables: undefined,
        status: 'idle',
        isPaused: false,
      } as never
    }
    return {
      mutate: vi.fn(),
      mutateAsync: vi.fn(),
      isPending: false,
      isIdle: true,
      isSuccess: false,
      isError: false,
      error: null,
      data: null,
      reset: vi.fn(),
      failureCount: 0,
      failureReason: null,
      context: undefined,
      submittedAt: 0,
      variables: undefined,
      status: 'idle',
      isPaused: false,
    } as never
  })
}

describe('IntegrationProjectsList (via IntegrationDetail)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows "Assigned projects" label when scope is project', () => {
    setupMocks({ integration: { scope: 'project' } })
    render(<IntegrationDetail />, { wrapper })

    expect(screen.getByText('Assigned projects')).toBeInTheDocument()
  })

  it('does not show "Assigned projects" label when scope is global', () => {
    setupMocks({ integration: { scope: 'global' } })
    render(<IntegrationDetail />, { wrapper })

    expect(screen.queryByText('Assigned projects')).not.toBeInTheDocument()
  })

  it('renders project names when scope is project and assignments exist', () => {
    setupMocks({ integration: { scope: 'project' } })
    render(<IntegrationDetail />, { wrapper })

    expect(screen.getByText('Alpha Project')).toBeInTheDocument()
    expect(screen.getByText('Beta Project')).toBeInTheDocument()
  })

  it('renders dash when scope is project and no assignments exist', () => {
    setupMocks({
      integration: { scope: 'project' },
      projectsData: { resources: [] },
    })
    render(<IntegrationDetail />, { wrapper })

    expect(screen.getByText('Assigned projects')).toBeInTheDocument()
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('renders skeleton while projects are loading', () => {
    setupMocks({
      integration: { scope: 'project' },
      projectsPending: true,
    })
    render(<IntegrationDetail />, { wrapper })

    expect(screen.getByText('Assigned projects')).toBeInTheDocument()
    expect(screen.queryByText('default')).not.toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })

  it('does not render assigned projects section when integration has no id', () => {
    setupMocks({
      integration: { id: undefined, scope: 'project' } as unknown as Partial<IntegrationRead>,
    })
    render(<IntegrationDetail />, { wrapper })

    expect(screen.queryByText('Assigned projects')).not.toBeInTheDocument()
  })

  describe('accessibility', () => {
    it('has no accessibility violations with assigned projects displayed', async () => {
      setupMocks({ integration: { scope: 'project' } })
      const { container } = render(<IntegrationDetail />, { wrapper })

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })
})
