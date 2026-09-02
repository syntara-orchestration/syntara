import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { workflowClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { searchParamsMock } from '../../../test/searchParamsMock'
import { routerTestState } from '../../../test/setup'
import { accessClient } from '../../access/accessClient'
import { useWorkflowPermissions } from '../../workflows/useWorkflowPermissions'

import { ProjectWorkflowsTab } from './ProjectWorkflowsTab'

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const { mockWorkflowPermissions } = vi.hoisted(() => ({
  mockWorkflowPermissions: {
    current: {
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      canRun: true,
      isLoading: false,
      tooltips: {
        create: 'create tooltip',
        duplicate: 'duplicate tooltip',
        update: 'update tooltip',
        delete: 'delete tooltip',
        run: 'run tooltip',
      },
    },
  },
}))

vi.mock('../../workflows/useWorkflowPermissions', () => ({
  useWorkflowPermissions: vi.fn(() => mockWorkflowPermissions.current),
}))

vi.mock('../../../hooks/routing/useSearchParams', async () => {
  const { useState, useEffect } = await import('react')
  const { searchParamsMock: mock } = await import('../../../test/searchParamsMock')
  return {
    useSearchParams: () => {
      const [, forceRender] = useState(0)
      useEffect(() => mock.subscribe(() => forceRender((n) => n + 1)), [])
      return [mock.get(), mock.set] as const
    },
  }
})

vi.mock('../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/system-administration/access-management/projects/proj-1/workflows',
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { routerTestState, MockLink } = await import('../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useNavigate: () => routerTestState.navigate,
  }
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockWorkflow = {
  id: 'wf-1',
  name: 'Project Alpha Workflow',
  description: 'Scoped workflow',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-06-01T00:00:00Z',
  is_enabled: true,
  project_id: 'proj-1',
  published_version_id: 'ver-1',
  current_version: 1,
  published_version_number: 1,
}

function mockQueries(options?: {
  resources?: (typeof mockWorkflow)[]
  next?: string | null
  total?: number
  isPending?: boolean
  error?: unknown
}) {
  const refetch = vi.fn().mockResolvedValue({})
  const returnValue = {
    data:
      options?.isPending || options?.error
        ? undefined
        : {
            resources: options?.resources ?? [mockWorkflow],
            next: options?.next ?? null,
            prev: null,
            total: options?.total ?? (options?.resources ?? [mockWorkflow]).length,
          },
    isPending: options?.isPending ?? false,
    isFetching: false,
    isError: Boolean(options?.error),
    error: options?.error ?? null,
    refetch,
  }
  vi.mocked(accessClient.useQuery).mockReturnValue(returnValue as never)
  vi.mocked(workflowClient.useQuery).mockReturnValue(returnValue as never)
  return refetch
}

describe('ProjectWorkflowsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    searchParamsMock.reset()
    mockWorkflowPermissions.current = {
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      canRun: true,
      isLoading: false,
      tooltips: {
        create: 'create tooltip',
        duplicate: 'duplicate tooltip',
        update: 'update tooltip',
        delete: 'delete tooltip',
        run: 'run tooltip',
      },
    }
    mockQueries()
  })

  it('has no accessibility violations with workflows', async () => {
    const { container } = render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations in the empty state', async () => {
    mockQueries({ resources: [] })
    const { container } = render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })
    expect(await axe(container)).toHaveNoViolations()
  })

  it('queries workflows for the open project via project_id', () => {
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(useWorkflowPermissions).toHaveBeenCalledWith({ resourceProject: 'proj-1' })
    expect(accessClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/projects/{project_id}/workflows',
      expect.objectContaining({
        params: expect.objectContaining({
          path: { project_id: 'proj-1' },
          query: expect.objectContaining({
            project_id: 'proj-1',
          }) as unknown,
        }) as unknown,
      }) as unknown,
      expect.anything()
    )
  })

  it('renders the scoped workflow name as a link to the builder', () => {
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    const link = screen.getByRole('link', { name: 'Project Alpha Workflow' })
    expect(link).toHaveAttribute('href', '/workflow-builder/wf-1')
  })

  it('does not render mutating row kebabs in the read-only project view', () => {
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(screen.queryByRole('button', { name: 'Actions for Project Alpha Workflow' })).not.toBeInTheDocument()
  })

  it('shows true empty messaging and create action when the project has no workflows', async () => {
    mockQueries({ resources: [] })
    const user = userEvent.setup()
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('No workflows yet')).toBeInTheDocument()
    expect(screen.getByText('Create your first workflow to get started.')).toBeInTheDocument()
    expect(screen.queryByText('No results found')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Create workflow' }))
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflow-builder/new' })
  })

  it('hides the create action when the user cannot create workflows', () => {
    mockWorkflowPermissions.current = { ...mockWorkflowPermissions.current, canCreate: false }
    mockQueries({ resources: [] })
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('No workflows yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create workflow' })).not.toBeInTheDocument()
  })

  it('hides the create action for builtin projects', () => {
    mockQueries({ resources: [] })
    render(<ProjectWorkflowsTab projectId="proj-1" isBuiltin />, { wrapper })

    expect(screen.queryByRole('button', { name: 'Create workflow' })).not.toBeInTheDocument()
  })

  it('shows filtered-empty messaging when filters match no rows', async () => {
    mockQueries({ resources: [] })
    searchParamsMock.set(new URLSearchParams('name[contains]=nomatch'))
    const user = userEvent.setup()
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('No results found')).toBeInTheDocument()
    expect(screen.queryByText('No workflows yet')).not.toBeInTheDocument()

    const clearButtons = screen.getAllByRole('button', { name: 'Clear all filters' })
    await user.click(clearButtons[clearButtons.length - 1])
    expect(searchParamsMock.get().toString()).not.toContain('name[contains]')
  })

  it('renders the same filter toolbar and sortable columns as the main Workflows list', () => {
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Name/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Created at/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Updated at/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /State/i })).toBeInTheDocument()

    const nameHeader = screen.getByRole('columnheader', { name: /Name/i })
    expect(within(nameHeader).getByRole('button')).toBeInTheDocument()
  })

  it('renders cursor pagination footer matching the main list', () => {
    mockQueries({ resources: [mockWorkflow], next: 'cursor-2', total: 40 })
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument()
  })

  it('defaults the workflows query sort to -updated_at', () => {
    render(<ProjectWorkflowsTab projectId="proj-1" />, { wrapper })

    expect(accessClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/projects/{project_id}/workflows',
      expect.objectContaining({
        params: expect.objectContaining({
          query: expect.objectContaining({
            sort: '-updated_at',
          }) as unknown,
        }) as unknown,
      }) as unknown,
      expect.anything()
    )
  })
})
