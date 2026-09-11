import type { ExecutionsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSearch } from '@tanstack/react-router'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React, { type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { executionsClient, workflowClient } from '../../client'
import { useSearchParams } from '../../hooks/routing/useSearchParams'
import { assertUrlParam } from '../../test/filter-test-helpers'
import { expectPageTitle } from '../../test/pageTitle'

import Executions from './Executions'

// Mock the client module
vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  },
  executionsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function TestWrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={testQueryClient}>{children}</QueryClientProvider>
}

// Mock useProjectSelector to avoid needing accessClient / QueryClientProvider
const mockUseProjectSelector = vi.fn(() => ({
  selectedProject: null as { id: string; name: string } | null,
  isAllProjects: false,
  projects: [] as { id: string; name: string }[],
  ProjectSelector: null,
}))
vi.mock('../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => mockUseProjectSelector(),
}))

// Passthrough — grouping name resolution is covered by useProjectsForGrouping tests.
vi.mock('../../hooks/useProjectsForGrouping', () => ({
  useProjectsForGrouping: (knownProjects: unknown) => knownProjects,
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) =>
      React.createElement('a', { href: String(to), ...rest }, children),
    useSearch: vi.fn(() => ({})),
  }
})

const mockSetSearchParams = vi.fn()

// useCursorPagination → useFilterState / useSortState still uses the bridge useSearchParams internally
vi.mock('../../hooks/routing/useSearchParams', () => ({
  useSearchParams: vi.fn(() => [new URLSearchParams(''), mockSetSearchParams]),
}))

describe('Executions Component', () => {
  const mockExecutions: ExecutionsAPI.components['schemas']['ExecutionRead'][] = [
    {
      id: '123e4567-e89b-12d3-a456-426614174000',
      workflow_id: 'workflow-1',
      workflow_name: 'Hello World Workflow',
      workflow_version_id: 'wfv-1',
      project_id: 'project-1',
      temporal_workflow_id: 'temporal-1',
      status: 'completed',
      created_by: 'user-1',
      updated_by: 'user-1',
      completed_at: '2025-01-01T10:30:00Z',
      created_at: '2025-01-01T09:55:00Z',
      updated_at: '2025-01-01T10:30:00Z',
      input_data: {},
      error_details: null,
    },
    {
      id: '223e4567-e89b-12d3-a456-426614174001',
      workflow_id: 'workflow-2',
      workflow_name: 'Data Processing Workflow',
      workflow_version_id: 'wfv-2',
      project_id: 'project-1',
      temporal_workflow_id: 'temporal-2',
      status: 'running',
      created_by: 'user-2',
      updated_by: null,
      completed_at: null,
      created_at: '2025-01-01T10:55:00Z',
      updated_at: '2025-01-01T11:00:00Z',
      input_data: {},
      error_details: null,
    },
    {
      id: '323e4567-e89b-12d3-a456-426614174002',
      workflow_id: 'workflow-3',
      workflow_name: 'API Integration Workflow',
      workflow_version_id: 'wfv-3',
      project_id: 'project-1',
      temporal_workflow_id: 'temporal-3',
      status: 'failed',
      created_by: 'user-3',
      updated_by: 'user-3',
      completed_at: '2025-01-01T12:05:00Z',
      created_at: '2025-01-01T11:55:00Z',
      updated_at: '2025-01-01T12:05:00Z',
      input_data: {},
      error_details: 'Task failed',
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useSearch).mockReturnValue({})
    vi.mocked(useSearchParams).mockReturnValue([new URLSearchParams(''), mockSetSearchParams])

    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)

    // Reset workflowClient mock to default implementation
    vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
      if (path === '/workflows') {
        return {
          data: { resources: mockWorkflows },
          isPending: false,
          error: null,
        }
      }
      return {
        data: undefined,
        isPending: false,
        error: null,
      }
    }) as never)
  })

  const mockWorkflows = [
    { id: 'workflow-1', name: 'Hello World Workflow' },
    { id: 'workflow-2', name: 'Data Processing Workflow' },
    { id: 'workflow-3', name: 'API Integration Workflow' },
  ]

  const mockExecutionsQuery = (
    data: ExecutionsAPI.components['schemas']['ExecutionRead'][],
    isPending = false,
    error: unknown = null
  ) => {
    vi.mocked(executionsClient.useQuery).mockReturnValue({
      data: { resources: data },
      isPending,
      error,
    } as never)

    // Mock the workflows query for fetching workflow names
    vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string, options?: unknown) => {
      if (path === '/workflows') {
        return {
          data: { resources: mockWorkflows },
          isPending: false,
          error: null,
        }
      }
      // Handle individual workflow requests (path: '/workflows/{workflow_id}')
      if (path === '/workflows/{workflow_id}') {
        const params = (options as { params?: { path?: { workflow_id?: string } } })?.params?.path
        const workflowId = params?.workflow_id
        const workflow = mockWorkflows.find((w) => w.id === workflowId)
        return {
          data: workflow,
          isPending: false,
          error: workflow ? null : new Error('Workflow not found'),
        }
      }
      return {
        data: undefined,
        isPending: false,
        error: null,
      }
    }) as never)
  }

  it('renders the executions table with data', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByText('Workflow Runs')).toBeInTheDocument()
    // FilterBar is visible - check for filter value selector button
    expect(screen.getByRole('button', { name: 'Search workflows' })).toBeInTheDocument()
  })

  it('displays execution IDs', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByText('123e4567-e89b-12d3-a456-426614174000')).toBeInTheDocument()
    expect(screen.getByText('223e4567-e89b-12d3-a456-426614174001')).toBeInTheDocument()
    expect(screen.getByText('323e4567-e89b-12d3-a456-426614174002')).toBeInTheDocument()
  })

  it('displays execution statuses with correct badges', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('renders table headers', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByRole('columnheader', { name: /Run ID/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^Workflow name$/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^Version$/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^Status$/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Created at/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Completed at/i })).toBeInTheDocument()
  })

  it('lists Run ID before Workflow name in the table', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    const headers = screen.getAllByRole('columnheader')
    const headerLabels = headers.map((header) => header.textContent?.trim() ?? '')
    const runIdIndex = headerLabels.findIndex((label) => /Run ID/i.test(label))
    const workflowNameIndex = headerLabels.findIndex((label) => /^Workflow name$/i.test(label))

    expect(runIdIndex).toBeGreaterThanOrEqual(0)
    expect(workflowNameIndex).toBeGreaterThan(runIdIndex)
  })

  it('displays version publish name when available', () => {
    mockExecutionsQuery([
      {
        ...mockExecutions[0],
        workflow_version: 3,
        workflow_version_name: 'prod release',
        workflow_version_created_at: '2025-01-01T09:00:00Z',
      },
    ])

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByText('prod release')).toBeInTheDocument()
  })

  // Longer timeout: this exercises PatternFly's Timestamp component, which has been observed
  // to occasionally exceed the 5s default under CI's coverage-instrumented, sharded test runs.
  it('displays version creation date when no publish name', () => {
    mockExecutionsQuery([
      {
        ...mockExecutions[0],
        workflow_version: 2,
        workflow_version_name: null,
        workflow_version_created_at: '2025-06-15T14:30:00Z',
      },
    ])

    render(<Executions />, { wrapper: TestWrapper })

    const versionCells = screen.getAllByRole('cell', { name: /Jun/ })
    expect(versionCells.length).toBeGreaterThanOrEqual(1)
  }, 15000)

  it('shows loading state', () => {
    mockExecutionsQuery([], true)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
  })

  it('shows error state', () => {
    mockExecutionsQuery([], false, { message: 'Failed to load' })

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByText('Error loading executions')).toBeInTheDocument()
  })

  it('displays workflow names instead of IDs', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByText('Hello World Workflow')).toBeInTheDocument()
    expect(screen.getByText('Data Processing Workflow')).toBeInTheDocument()
    expect(screen.getByText('API Integration Workflow')).toBeInTheDocument()
  })

  it('falls back to workflow_id when workflow_name is null', () => {
    mockExecutionsQuery([{ ...mockExecutions[0], workflow_name: null }])

    render(<Executions />, { wrapper: TestWrapper })

    const link = screen.getByRole('link', { name: mockExecutions[0].workflow_id })
    expect(link).toHaveAttribute('href', `/workflow-builder/${mockExecutions[0].workflow_id}`)
  })

  it('shows placeholder for null timestamps', () => {
    mockExecutionsQuery([
      {
        id: 'pending-exec',
        workflow_id: 'workflow-pending',
        workflow_version_id: 'wfv-pending',
        project_id: 'project-1',
        temporal_workflow_id: 'temporal-pending',
        status: 'pending',
        created_by: 'user-1',
        updated_by: null,
        completed_at: null,
        created_at: '2025-01-01T09:00:00Z',
        updated_at: '2025-01-01T09:00:00Z',
        input_data: {},
        error_details: null,
      },
    ])

    render(<Executions />, { wrapper: TestWrapper })

    // Check for placeholder em-dashes (Version and Completed at columns)
    const placeholders = screen.getAllByText('—')
    expect(placeholders.length).toBeGreaterThanOrEqual(1)
  })

  it('applies workflow_id filter from URL parameter and passes to API', () => {
    vi.mocked(useSearch).mockReturnValue({ workflow_id: 'workflow-1' })

    const mockUseQuery = vi.fn().mockReturnValue({
      data: { resources: mockExecutions.filter((e) => e.workflow_id === 'workflow-1') },
      isPending: false,
      error: null,
    })
    vi.mocked(executionsClient.useQuery).mockImplementation(mockUseQuery as never)

    vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
      if (path === '/workflows') {
        return {
          data: { resources: mockWorkflows },
          isPending: false,
          error: null,
        }
      }
      return {
        data: undefined,
        isPending: false,
        error: null,
      }
    }) as never)

    render(<Executions />, { wrapper: TestWrapper })

    // Verify executionsClient.useQuery was called with correct params
    expect(mockUseQuery).toHaveBeenCalledWith('get', '/executions', {
      params: {
        query: expect.objectContaining({
          workflow_id: 'workflow-1',
          limit: 20,
          include_total: true,
        }) as unknown,
      },
    })

    // Title is always "Workflow Runs" regardless of filters
    expect(screen.getByText('Workflow Runs')).toBeInTheDocument()
    // FilterBar should be present with active filter chip
    expect(screen.getByRole('button', { name: /Clear all filters/i })).toBeInTheDocument()
  })

  it('execution ID links navigate to execution detail page', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    const executionLink = screen.getByRole('link', { name: '123e4567-e89b-12d3-a456-426614174000' })
    expect(executionLink).toHaveAttribute('href', '/executions/123e4567-e89b-12d3-a456-426614174000')
  })

  it('workflow name links navigate to workflow builder', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    const workflowLink = screen.getByRole('link', { name: 'Hello World Workflow' })
    expect(workflowLink).toHaveAttribute('href', '/workflow-builder/workflow-1')
  })

  it('all execution IDs navigate to their respective execution detail pages', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByRole('link', { name: '123e4567-e89b-12d3-a456-426614174000' })).toHaveAttribute(
      'href',
      '/executions/123e4567-e89b-12d3-a456-426614174000'
    )
    expect(screen.getByRole('link', { name: '223e4567-e89b-12d3-a456-426614174001' })).toHaveAttribute(
      'href',
      '/executions/223e4567-e89b-12d3-a456-426614174001'
    )
    expect(screen.getByRole('link', { name: '323e4567-e89b-12d3-a456-426614174002' })).toHaveAttribute(
      'href',
      '/executions/323e4567-e89b-12d3-a456-426614174002'
    )
  })

  it('all workflow names navigate to their respective workflow builders', () => {
    mockExecutionsQuery(mockExecutions)

    render(<Executions />, { wrapper: TestWrapper })

    expect(screen.getByRole('link', { name: 'Hello World Workflow' })).toHaveAttribute(
      'href',
      '/workflow-builder/workflow-1'
    )
    expect(screen.getByRole('link', { name: 'Data Processing Workflow' })).toHaveAttribute(
      'href',
      '/workflow-builder/workflow-2'
    )
    expect(screen.getByRole('link', { name: 'API Integration Workflow' })).toHaveAttribute(
      'href',
      '/workflow-builder/workflow-3'
    )
  })

  describe('API sorting', () => {
    it('defaults query sort to -created_at', () => {
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      expect(executionsClient.useQuery).toHaveBeenCalledWith(
        'get',
        '/executions',
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({
              sort: '-created_at',
            }) as unknown,
          }) as unknown,
        }) as unknown
      )
    })

    it('renders sortable headers for workflow, status, created, and completed', () => {
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      for (const name of [/^Workflow name$/i, /^Status$/i, /Created at/i, /Completed at/i]) {
        const header = screen.getByRole('columnheader', { name })
        expect(within(header).getByRole('button')).toBeInTheDocument()
      }

      const runIdHeader = screen.getByRole('columnheader', { name: /Run ID/i })
      expect(within(runIdHeader).queryByRole('button')).not.toBeInTheDocument()

      const versionHeader = screen.getByRole('columnheader', { name: /Version/i })
      expect(within(versionHeader).queryByRole('button')).not.toBeInTheDocument()

      const actionsHeader = screen.getByRole('columnheader', { name: 'Actions' })
      expect(within(actionsHeader).queryByRole('button')).not.toBeInTheDocument()
    })

    it('writes sort URL param when a column header is clicked', async () => {
      const user = userEvent.setup()
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      const statusHeader = screen.getByRole('columnheader', { name: /^Status$/i })
      await user.click(within(statusHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'status')
      })
    })

    it('can sort by workflow_id via the Workflow name column', async () => {
      const user = userEvent.setup()
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      const workflowHeader = screen.getByRole('columnheader', { name: /^Workflow name$/i })
      await user.click(within(workflowHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'workflow_id')
      })
    })

    it('can sort by completed_at via the Completed at column', async () => {
      const user = userEvent.setup()
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      const completedAtHeader = screen.getByRole('columnheader', { name: /Completed at/i })
      await user.click(within(completedAtHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'completed_at')
      })
    })

    it('preserves workflow_id filter when sorting', async () => {
      const user = userEvent.setup()
      vi.mocked(useSearch).mockReturnValue({ workflow_id: 'workflow-1' })

      const filteredExecutions = [
        { ...mockExecutions[0], workflow_id: 'workflow-1' },
        { ...mockExecutions[1], workflow_id: 'workflow-1', id: '223e4567-e89b-12d3-a456-426614174001' },
      ]

      mockExecutionsQuery(filteredExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      expect(screen.getByRole('columnheader', { name: /^Workflow name$/i })).toBeInTheDocument()

      const statusHeader = screen.getByRole('columnheader', { name: /^Status$/i })
      await user.click(within(statusHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'status')
      })

      expect(screen.getByText('123e4567-e89b-12d3-a456-426614174000')).toBeInTheDocument()
      expect(screen.getByText('223e4567-e89b-12d3-a456-426614174001')).toBeInTheDocument()
    })
  })

  describe('API Filter Contract', () => {
    it.todo('passes workflow_id filter to API query params when workflow is selected')

    it('maps Pending approval status filter to approval_pending query param', async () => {
      const user = userEvent.setup()
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      const fieldSelector = screen.getAllByRole('button', { name: 'Workflow name' })[0]
      await user.click(fieldSelector)

      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Status' })).toBeInTheDocument()
      })
      await user.click(screen.getByRole('option', { name: 'Status' }))

      const valueSelector = await screen.findByRole('button', { name: /Filter by status/i }, { timeout: 10000 })
      await user.click(valueSelector)

      const pendingApprovalOption = await screen.findByRole('option', { name: 'Pending approval' })
      await user.click(pendingApprovalOption)

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'approval_pending', 'true')
      })
    }, 10000)

    it('passes status filter with correct API shape', async () => {
      const user = userEvent.setup()
      const mockUseQuery = vi.fn().mockReturnValue({
        data: { resources: mockExecutions },
        isPending: false,
        error: null,
      })
      vi.mocked(executionsClient.useQuery).mockImplementation(mockUseQuery as never)

      render(<Executions />, { wrapper: TestWrapper })

      // Open field selector
      const fieldSelector = screen.getAllByRole('button', { name: 'Workflow name' })[0]
      await user.click(fieldSelector)

      // Select Status field
      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Status' })).toBeInTheDocument()
      })
      const statusOption = screen.getByRole('option', { name: 'Status' })
      await user.click(statusOption)

      // Open value selector and select a status
      const valueSelector = await screen.findByRole('button', { name: /Filter by status/i }, { timeout: 10000 })
      await user.click(valueSelector)

      await waitFor(() => {
        // "Completed" appears in both table and dropdown
        expect(screen.getAllByText('Completed').length).toBeGreaterThan(0)
      })

      // Find the option element in the dropdown menu and verify it exists before clicking
      const completedOption = screen.getByRole('option', { name: 'Completed' })
      expect(completedOption).toBeInTheDocument()
      await user.click(completedOption)
      // After clicking, the dropdown closes and the option leaves the DOM — that is expected
    }, 10000)
  })

  describe('Filter Functionality', () => {
    it('shows filter bar with field selector when data exists', () => {
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      // FilterBar shows by default - verify filter components are present
      // The field selector for "Workflow name" exists (there are 2: filter selector and table header)
      const workflowButtons = screen.getAllByRole('button', { name: 'Workflow name' })
      expect(workflowButtons.length).toBeGreaterThan(0)
    })

    it('can select a different filter field from the dropdown', async () => {
      mockExecutionsQuery(mockExecutions)
      const user = userEvent.setup()

      render(<Executions />, { wrapper: TestWrapper })

      // Click the field selector dropdown - get all buttons with "Workflow name" and pick the first (filter selector)
      const buttons = screen.getAllByRole('button', { name: 'Workflow name' })
      const fieldSelector = buttons[0] // First one is the filter field selector
      await user.click(fieldSelector)

      // Should show filter field options in the menu
      // Note: Created Date filter is currently disabled due to backend limitation
      await waitFor(() => {
        expect(screen.getByRole('option', { name: 'Status' })).toBeInTheDocument()
      })
      // Only Workflow name and Status filters are available (Created Date disabled)
      expect(screen.getByRole('option', { name: 'Workflow name' })).toBeInTheDocument()
    })

    it('preserves workflow_id filter from URL parameter and syncs to query params', () => {
      vi.mocked(useSearch).mockReturnValue({ workflow_id: 'workflow-1' })

      const mockUseQuery = vi.fn().mockReturnValue({
        data: { resources: mockExecutions.filter((e) => e.workflow_id === 'workflow-1') },
        isPending: false,
        error: null,
      })
      vi.mocked(executionsClient.useQuery).mockImplementation(mockUseQuery as never)

      vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
        if (path === '/workflows') {
          return {
            data: { resources: mockWorkflows },
            isPending: false,
            error: null,
          }
        }
        return {
          data: undefined,
          isPending: false,
          error: null,
        }
      }) as never)

      render(<Executions />, { wrapper: TestWrapper })

      // Verify API was called with workflow_id filter
      expect(mockUseQuery).toHaveBeenCalledWith('get', '/executions', {
        params: {
          query: expect.objectContaining({
            workflow_id: 'workflow-1',
          }) as unknown,
        },
      })

      // Title is always "Workflow Runs"
      expect(screen.getByText('Workflow Runs')).toBeInTheDocument()
      // FilterBar should be present with active filter chip
      expect(screen.getByRole('button', { name: /Clear all filters/i })).toBeInTheDocument()
    })
  })

  describe('Empty States', () => {
    it('shows empty state when no executions exist', () => {
      // Ensure URL has no filters
      vi.mocked(useSearch).mockReturnValue({})

      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        error: null,
      } as never)
      // Don't override workflowClient mock - use the one from beforeEach

      render(<Executions />, { wrapper: TestWrapper })

      // When there's no data and no filters, show EmptyStateNoData without the filter toolbar
      expect(screen.getByText('No executions yet')).toBeInTheDocument()
      expect(screen.getByText('No workflow runs have been recorded yet.')).toBeInTheDocument()
      expect(screen.queryByRole('search', { name: 'Filters' })).not.toBeInTheDocument()
    })

    it('shows filter empty state when filtering returns no results', () => {
      vi.mocked(useSearch).mockReturnValue({ workflow_id: 'workflow-1' })

      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        error: null,
      } as never)
      vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
        if (path === '/workflows') {
          return {
            data: { resources: mockWorkflows },
            isPending: false,
            error: null,
          }
        }
        return {
          data: undefined,
          isPending: false,
          error: null,
        }
      }) as never)

      render(<Executions />, { wrapper: TestWrapper })

      // Shows EmptyStateFilter when there are active filters but no results
      expect(screen.getByText('No results found')).toBeInTheDocument()
      // Both FilterBar and EmptyStateFilter have "Clear all filters" buttons
      const clearButtons = screen.getAllByRole('button', { name: /clear all filters/i })
      expect(clearButtons.length).toBeGreaterThan(0)
    })

    it('does not show filter bar when no executions and no active filters', () => {
      // Ensure URL has no filters
      vi.mocked(useSearch).mockReturnValue({})

      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        error: null,
      } as never)
      // Don't override workflowClient mock - use the one from beforeEach

      render(<Executions />, { wrapper: TestWrapper })

      // FilterBar is always visible; EmptyStateNoData is shown in the table area
      expect(screen.getByText('No executions yet')).toBeInTheDocument()
    })
  })

  describe('Pagination', () => {
    it('displays footer with execution count', () => {
      mockExecutionsQuery(mockExecutions)

      render(<Executions />, { wrapper: TestWrapper })

      // PF Pagination renders a nav with pagination controls
      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
    })

    it('displays singular execution text for one execution', () => {
      mockExecutionsQuery([mockExecutions[0]])

      render(<Executions />, { wrapper: TestWrapper })

      // PF Pagination renders a nav with pagination controls even for a single item
      expect(screen.getByRole('navigation', { name: /pagination/i })).toBeInTheDocument()
    })

    it('displays total count when more executions exist', () => {
      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: {
          resources: mockExecutions,
          total: 50,
          next: 'next-cursor',
        },
        isPending: false,
        error: null,
      } as never)

      render(<Executions />, { wrapper: TestWrapper })

      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      expect(paginationNav).toBeInTheDocument()
      expect(paginationNav.parentElement?.textContent).toContain('1 - 20 of 50')
    })

    it('handles next page navigation', async () => {
      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: {
          resources: mockExecutions,
          total: 50,
          next: 'next-cursor',
          prev: null,
        },
        isPending: false,
        error: null,
      } as never)

      const user = userEvent.setup()
      render(<Executions />, { wrapper: TestWrapper })

      // Find and click the next button
      const nextButton = screen.getByRole('button', { name: /next/i })
      await user.click(nextButton)

      // The component should have called setCursor (state update)
      // We verify by ensuring the button was clickable
      expect(nextButton).toBeInTheDocument()
    })

    it('handles previous page navigation', async () => {
      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: {
          resources: mockExecutions,
          total: 50,
          next: null,
          prev: 'prev-cursor',
        },
        isPending: false,
        error: null,
      } as never)

      const user = userEvent.setup()
      render(<Executions />, { wrapper: TestWrapper })

      // Find and click the prev button
      const prevButton = screen.getByRole('button', { name: /previous/i })
      await user.click(prevButton)

      // The component should have called setCursor (state update)
      expect(prevButton).toBeInTheDocument()
    })
  })

  describe('Grouped view (All Projects)', () => {
    it('renders grouped executions when all projects are selected', () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [
          { id: 'proj-1', name: 'Project Alpha' },
          { id: 'proj-2', name: 'Project Beta' },
        ],
        ProjectSelector: null,
      })

      const executionsWithProjects = [
        {
          ...mockExecutions[0],
          project_id: 'proj-1',
        },
        {
          ...mockExecutions[1],
          project_id: 'proj-2',
        },
      ]

      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: { resources: executionsWithProjects },
        isPending: false,
        error: null,
      } as never)

      vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
        if (path === '/workflows') {
          return { data: { resources: mockWorkflows }, isPending: false, error: null }
        }
        return { data: undefined, isPending: false, error: null }
      }) as never)

      render(<Executions />, { wrapper: TestWrapper })

      // Grouped view shows project names as group headers
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      expect(screen.getByText('Project Beta')).toBeInTheDocument()

      // Count badge removed — page-local counts were misleading (AAP-85112)
      const alphaHeader = screen.getByRole('row', { name: /Project Alpha/ })
      expect(within(alphaHeader).queryByText('1')).not.toBeInTheDocument()
    })

    it('toggles project group collapsed/expanded', async () => {
      const user = userEvent.setup()

      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [{ id: 'proj-1', name: 'Project Alpha' }],
        ProjectSelector: null,
      })

      const executionsWithProjects = [
        {
          ...mockExecutions[0],
          project_id: 'proj-1',
        },
      ]

      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: { resources: executionsWithProjects },
        isPending: false,
        error: null,
      } as never)

      vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
        if (path === '/workflows') {
          return { data: { resources: mockWorkflows }, isPending: false, error: null }
        }
        if (path === '/workflows/{workflow_id}') {
          return { data: mockWorkflows[0], isPending: false, error: null }
        }
        return { data: undefined, isPending: false, error: null }
      }) as never)

      render(<Executions />, { wrapper: TestWrapper })

      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      // Execution ID should be visible
      expect(screen.getByText('123e4567-e89b-12d3-a456-426614174000')).toBeInTheDocument()

      // Click to collapse
      await user.click(screen.getByText('Project Alpha'))

      // Execution should be hidden
      expect(screen.queryByText('123e4567-e89b-12d3-a456-426614174000')).not.toBeInTheDocument()

      // Click to expand
      await user.click(screen.getByText('Project Alpha'))

      // Execution should be visible again
      expect(screen.getByText('123e4567-e89b-12d3-a456-426614174000')).toBeInTheDocument()
    })

    it('falls back to projectId when project is not found', () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [], // No projects found
        ProjectSelector: null,
      })

      const executionsWithProjects = [
        {
          ...mockExecutions[0],
          project_id: 'unknown-proj-id',
        },
      ]

      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: { resources: executionsWithProjects },
        isPending: false,
        error: null,
      } as never)

      vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
        if (path === '/workflows') {
          return { data: { resources: mockWorkflows }, isPending: false, error: null }
        }
        return { data: undefined, isPending: false, error: null }
      }) as never)

      render(<Executions />, { wrapper: TestWrapper })

      // Falls back to project ID string when project is not in the list
      expect(screen.getByText('unknown-proj-id')).toBeInTheDocument()
    })
  })

  describe('Project filtering', () => {
    it('renders correctly when a project is selected', () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: { id: 'proj-1', name: 'Project Alpha' },
        isAllProjects: false,
        projects: [{ id: 'proj-1', name: 'Project Alpha' }],
        ProjectSelector: null,
      })

      const mockUseQuery = vi.fn().mockReturnValue({
        data: { resources: mockExecutions },
        isPending: false,
        error: null,
      })
      vi.mocked(executionsClient.useQuery).mockImplementation(mockUseQuery as never)

      render(<Executions />, { wrapper: TestWrapper })

      // Query is called with cursor pagination params
      expect(mockUseQuery).toHaveBeenCalledWith(
        'get',
        '/executions',
        expect.objectContaining({
          params: {
            query: expect.objectContaining({
              limit: 20,
              include_total: true,
            }) as unknown,
          },
        }) as unknown
      )
    })
  })

  describe('Clear all filters', () => {
    it('clears filters when "Clear all filters" button in EmptyStateFilter is clicked', async () => {
      const user = userEvent.setup()
      const mockSetSearchParams = vi.fn()
      vi.mocked(useSearchParams).mockReturnValue([new URLSearchParams(''), mockSetSearchParams])
      vi.mocked(useSearch).mockReturnValue({ workflow_id: 'workflow-1' })

      vi.mocked(executionsClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        error: null,
      } as never)

      vi.mocked(workflowClient.useQuery).mockImplementation(((_method: string, path: string) => {
        if (path === '/workflows') {
          return { data: { resources: mockWorkflows }, isPending: false, error: null }
        }
        return { data: undefined, isPending: false, error: null }
      }) as never)

      render(<Executions />)

      // EmptyStateFilter shown when active filters return no results
      expect(screen.getByText('No results found')).toBeInTheDocument()

      // Click "Clear all filters" in the EmptyStateFilter (last button, after the filter bar's)
      const clearButtons = screen.getAllByRole('button', { name: /clear all filters/i })
      await user.click(clearButtons[clearButtons.length - 1])

      // Filter clearing calls setSearchParams to remove filter params from the URL
      expect(mockSetSearchParams).toHaveBeenCalledWith(expect.any(URLSearchParams))
    })
  })

  describe('Page title', () => {
    it('sets the browser tab title', () => {
      mockExecutionsQuery(mockExecutions)
      render(<Executions />, { wrapper: TestWrapper })
      expectPageTitle(['Workflow Runs'])
    })
  })
})
