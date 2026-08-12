import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { executionsFetchClient, workflowClient, workflowFetchClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { ColorSchemeProvider } from '../../providers/theme/ColorSchemeProvider'
import { assertUrlParam, assertUrlParamIsNull } from '../../test/filter-test-helpers'
import { expectPageTitle } from '../../test/pageTitle'
import { routerTestState } from '../../test/setup'
import { accessClient } from '../access/accessClient'

import Workflows from './Workflows'

// Mock dependencies
vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  executionsClient: {
    useQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  },
  executionsFetchClient: {
    POST: vi.fn(),
  },
  workflowFetchClient: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../access/useAllProjects', () => ({
  useAllProjects: vi.fn(() => ({ projects: [], isLoading: false, error: null, refetch: vi.fn() })),
  useSelectableProjects: vi.fn(() => ({ projects: [], isLoading: false, error: null, refetch: vi.fn() })),
}))

// Mock useProjectSelector — default to a single selected project so that:
// 1. projectSelectorReady is true (queries are enabled)
// 2. the flat table body is rendered (most tests expect flat rows)
const mockUseProjectSelector = vi.fn(() => ({
  selectedProject: { id: 'proj-default', name: 'Default Project' } as { id: string; name: string } | null,
  isAllProjects: false,
  projects: [{ id: 'proj-default', name: 'Default Project' }],
  ProjectSelector: null,
}))
vi.mock('../../hooks/useProjectSelector', () => ({
  useProjectSelector: () => mockUseProjectSelector(),
}))

// Passthrough — grouping name resolution is covered by useProjectsForGrouping tests.
vi.mock('../../hooks/useProjectsForGrouping', () => ({
  useProjectsForGrouping: (knownProjects: unknown) => knownProjects,
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
        update: 'update tooltip',
        delete: 'delete tooltip',
        run: 'run tooltip',
      },
    },
  },
}))

vi.mock('./useWorkflowPermissions', () => ({
  useWorkflowPermissions: () => mockWorkflowPermissions.current,
}))

const mockSetSearchParams = vi.fn()

let mockSearchParams = new URLSearchParams()

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: () => '/workflows',
}))

vi.mock('../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}))

/** Sets the same return value on both workflowClient.useQuery and accessClient.useQuery */
function mockWorkflowQuery(returnValue: ReturnType<typeof workflowClient.useQuery>) {
  vi.mocked(workflowClient.useQuery).mockReturnValue(returnValue)
  vi.mocked(accessClient.useQuery).mockReturnValue(returnValue)
}

// Create a QueryClient instance
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <ColorSchemeProvider>
      <AlertProvider>{children}</AlertProvider>
    </ColorSchemeProvider>
  </QueryClientProvider>
)

describe('Workflows Component', () => {
  const mockWorkflows = [
    {
      id: '1',
      name: 'Important Project Workflow',
      description: 'Complex workflow for critical project',
      created_at: '2023-01-01T00:00:00Z',
      updated_at: '2023-01-02T00:00:00Z',
      is_enabled: true,
      project_id: 'project-1',
      published_version_id: 'version-1',
      labels: {
        type: 'critical',
        status: 'active',
      },
    },
    {
      id: '2',
      name: 'Secondary Team Workflow',
      description: 'Routine workflow for secondary tasks',
      created_at: '2023-02-01T00:00:00Z',
      updated_at: '2023-02-02T00:00:00Z',
      is_enabled: false,
      project_id: 'project-2',
      labels: {
        type: 'routine',
        status: 'maintenance',
      },
    },
  ]

  beforeEach(() => {
    // Reset mocks before each test
    mockSetSearchParams.mockClear()
    mockSearchParams = new URLSearchParams()
    mockWorkflowPermissions.current = {
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      canRun: true,
      isLoading: false,
      tooltips: { create: 'create tooltip', update: 'update tooltip', delete: 'delete tooltip', run: 'run tooltip' },
    }

    // Set up accessClient default return values FIRST
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)

    // Then set up workflow query (mockWorkflowQuery will override accessClient.useQuery)
    const defaultQueryReturn = {
      data: {
        resources: mockWorkflows,
        next: null,
        prev: null,
        total: mockWorkflows.length,
      },
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    }
    mockWorkflowQuery(defaultQueryReturn)

    const defaultMutationReturn = {
      mutateAsync: vi.fn(),
      reset: vi.fn(),
      isPending: false,
      isError: false,
      isSuccess: false,
      isIdle: true,
      error: null,
      data: undefined,
      variables: undefined,
      context: undefined,
      failureCount: 0,
      failureReason: null,
      status: 'idle' as const,
      submittedAt: 0,
    }

    // Mock workflowFetchClient.GET to return workflow detail with a trigger
    vi.mocked(workflowFetchClient.GET).mockResolvedValue({
      data: {
        id: '1',
        current_version: 1,
        published_version_number: 1,
        version: {
          workflow_definition: {
            triggers: [{ id: 'trigger-1', name: 'Manual Trigger', parameters: {} }],
          },
        },
      },
    } as never)

    // Mock executionsFetchClient.POST for execute workflow (success by default)
    vi.mocked(executionsFetchClient.POST).mockResolvedValue({
      data: { id: 'exec-default' },
      error: undefined,
    } as never)

    // Mock workflowClient.useMutation for delete workflow
    vi.mocked(workflowClient.useMutation).mockReturnValue({
      ...defaultMutationReturn,
      mutate: vi.fn(),
    })

    // Mock accessClient.useMutation for project delete
    vi.mocked(accessClient.useMutation).mockReturnValue({
      ...defaultMutationReturn,
      mutate: vi.fn(),
    })
  })

  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<Workflows />, { wrapper })

      // Check page header
      expect(screen.getByText('Workflows')).toBeInTheDocument()

      // Check table is rendered
      expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
    })

    it('sets the browser tab title', () => {
      render(<Workflows />, { wrapper })
      expectPageTitle(['Workflows'])
    })

    it('renders Import workflow button before Create workflow in toolbar', () => {
      render(<Workflows />, { wrapper })

      const importButton = screen.getByRole('button', { name: 'Import workflow' })
      const createButton = screen.getByRole('button', { name: 'Create workflow' })

      // Import workflow (secondary) must precede Create workflow (primary) in the DOM
      expect(importButton.compareDocumentPosition(createButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })

    it('renders workflows in the table', async () => {
      render(<Workflows />, { wrapper })

      // Wait for table to render (PF Table uses role="grid")
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Check workflow names are rendered
      expect(screen.getByText('Important Project Workflow')).toBeInTheDocument()
      expect(screen.getByText('Secondary Team Workflow')).toBeInTheDocument()
    })
  })

  describe('Filter Functionality', () => {
    it('renders FilterBar component without keyword search', () => {
      render(<Workflows />, { wrapper })

      // FilterBar should be present but keyword search input should not
      expect(screen.queryByPlaceholderText('Search workflows...')).not.toBeInTheDocument()

      // Table should still render
      expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
    })

    it('shows all workflows when no filters are active', async () => {
      render(<Workflows />, { wrapper })

      // Wait for table to render
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // All workflows should be visible
      expect(screen.getByText('Important Project Workflow')).toBeInTheDocument()
      expect(screen.getByText('Secondary Team Workflow')).toBeInTheDocument()
    })

    it('applies name filter to API query when typing and submitting', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      const nameInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(nameInput, 'deploy')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'name[contains]', 'deploy')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })

    it('resets pagination cursor when filters change', async () => {
      const user = userEvent.setup()

      // Start with pagination cursor in URL
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor',
          prev: 'prev-cursor',
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Workflows />, { wrapper })

      // Apply a filter
      const nameInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(nameInput, 'test')
      await user.keyboard('{Enter}')

      // Verify cursor was reset
      await waitFor(() => {
        assertUrlParamIsNull(mockSetSearchParams, 'cursor')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('displays loading state', () => {
      const loadingReturn = {
        data: null,
        isPending: true,
        isError: false,
        error: null,
      }
      mockWorkflowQuery(loadingReturn)

      render(<Workflows />, { wrapper })

      // Expect loading state
      const loadingElement = screen.getByTestId('loading-state')
      expect(loadingElement).toBeInTheDocument()
    })

    it('displays error state', () => {
      const mockError = new Error('Failed to load workflows')
      // NOTE: component may re-render due to AlertProvider updates; keep error stable across renders
      mockWorkflowQuery({
        data: null,
        isPending: false,
        isError: true,
        error: mockError,
      })

      render(<Workflows />, { wrapper })

      // Check for error state
      const errorElement = screen.getByTestId('error-state')
      expect(errorElement).toBeInTheDocument()
      // Title also appears in the global alert; scope to the error state container
      expect(within(errorElement).getByText('Error loading workflows')).toBeInTheDocument()
    })
  })

  describe('Table Columns', () => {
    it('renders name column with clickable links that navigate', () => {
      render(<Workflows />, { wrapper })

      const workflowLink = screen.getByText('Important Project Workflow')
      expect(workflowLink).toBeInTheDocument()

      const link = screen.getByRole('link', { name: 'Important Project Workflow' })
      expect(link).toHaveAttribute('href', '/workflow-builder/1')
    })
  })

  describe('Execute Workflow Row Action', () => {
    it('calls execute mutation when workflow is run', async () => {
      vi.mocked(executionsFetchClient.POST).mockResolvedValue({
        data: { id: 'exec-123' },
        error: undefined,
      } as never)

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Wait for table to render (PF Table uses role="grid")
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Find and click the row action button for the first workflow
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Find and click the menu trigger button (the actions menu button)
      // Actions column is always the last column, so the actions button is the last button in the row
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Wait for menu to open and click the "Run workflow" menu item
      const runWorkflowItem = await screen.findByText('Run published version')
      await user.click(runWorkflowItem)

      // Wait for confirmation dialog to appear and click "Run now" button
      const runButton = await screen.findByRole('button', { name: /^Run now$/i })
      await user.click(runButton)

      await waitFor(() => {
        expect(executionsFetchClient.POST).toHaveBeenCalledWith('/executions', {
          body: { workflow_id: '1', input_data: {}, trigger_node_id: 'trigger-1', use_published: true },
        })
      })
    })

    it('shows error alert when workflow execution fails', async () => {
      vi.mocked(executionsFetchClient.POST).mockResolvedValue({
        data: undefined,
        error: { detail: 'Network error' },
      } as never)

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Wait for table to render (PF Table uses role="grid")
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Find and click the row action button for the first workflow
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Find and click the menu trigger button (the actions menu button)
      // Actions column is always the last column, so the actions button is the last button in the row
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Wait for menu to open and click the "Run workflow" menu item
      const runWorkflowItem = await screen.findByText('Run published version')
      await user.click(runWorkflowItem)

      // Wait for confirmation dialog to appear and click "Run now" button
      const runButton = await screen.findByRole('button', { name: /^Run now$/i })
      await user.click(runButton)

      // Verify error alert is shown
      await waitFor(() => {
        expect(screen.getByText('Workflow failed')).toBeInTheDocument()
        expect(screen.getByText(/Failed to start workflow "Important Project Workflow"/)).toBeInTheDocument()
      })
    })

    it('shows error alert with generic message when error has no message', async () => {
      vi.mocked(executionsFetchClient.POST).mockResolvedValue({
        data: undefined,
        error: {},
      } as never)

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Wait for table to render (PF Table uses role="grid")
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Find and click the row action button for the first workflow
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Find and click the menu trigger button (the actions menu button)
      // Actions column is always the last column, so the actions button is the last button in the row
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Wait for menu to open and click the "Run workflow" menu item
      const runWorkflowItem = await screen.findByText('Run published version')
      await user.click(runWorkflowItem)

      // Wait for confirmation dialog to appear and click "Run now" button
      const runButton = await screen.findByRole('button', { name: /^Run now$/i })
      await user.click(runButton)

      // Verify error alert is shown with generic message
      await waitFor(() => {
        expect(screen.getByText('Workflow failed')).toBeInTheDocument()
        expect(
          screen.getByText(/Failed to start workflow "Important Project Workflow": An unexpected error occurred/)
        ).toBeInTheDocument()
      })
    })

    it('shows confirmation dialog when running workflow', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Wait for table to render (PF Table uses role="grid")
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Find and click the row action button for the first workflow
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Find and click the menu trigger button (the actions menu button)
      // Actions column is always the last column, so the actions button is the last button in the row
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Wait for menu to open and click the "Run workflow" menu item
      const runWorkflowItem = await screen.findByText('Run published version')
      await user.click(runWorkflowItem)

      // Verify confirmation dialog is shown
      await waitFor(() => {
        expect(screen.getByText('Run Important Project Workflow?')).toBeInTheDocument()
        expect(
          screen.getByText(
            /You are about to manually run this workflow. This action will start the workflow immediately, bypassing its normal trigger conditions./
          )
        ).toBeInTheDocument()
      })

      // Verify Run now and Cancel buttons are present
      expect(screen.getByRole('button', { name: /^Run now$/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Cancel/i })).toBeInTheDocument()
    })

    it('cancels workflow run when cancel button is clicked', async () => {
      vi.mocked(executionsFetchClient.POST).mockClear()

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Wait for table to render (PF Table uses role="grid")
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Find and click the row action button for the first workflow
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Find and click the menu trigger button (the actions menu button)
      // Actions column is always the last column, so the actions button is the last button in the row
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Wait for menu to open and click the "Run workflow" menu item
      const runWorkflowItem = await screen.findByText('Run published version')
      await user.click(runWorkflowItem)

      // Wait for confirmation dialog to appear and click "Cancel" button
      const cancelButton = await screen.findByRole('button', { name: /Cancel/i })
      await user.click(cancelButton)

      // Verify the fetch client was not called
      expect(executionsFetchClient.POST).not.toHaveBeenCalled()

      // Verify dialog is closed
      await waitFor(() => {
        expect(screen.queryByText('Run Important Project Workflow?')).not.toBeInTheDocument()
      })
    })

    it('shows input modal and sends collected input_data when trigger has input schema', async () => {
      vi.mocked(workflowFetchClient.GET).mockResolvedValue({
        data: {
          id: '1',
          current_version: 1,
          published_version_number: 1,
          version: {
            workflow_definition: {
              triggers: [
                {
                  id: 'trigger-1',
                  name: 'Manual Trigger',
                  parameters: {
                    input_schema: {
                      type: 'object',
                      properties: { version: { type: 'string' } },
                    },
                  },
                },
              ],
            },
          },
        },
      } as never)
      vi.mocked(executionsFetchClient.POST).mockResolvedValue({
        data: { id: 'exec-with-inputs' },
        error: undefined,
      } as never)

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const buttons = within(rows[1]).getAllByRole('button')
      await user.click(buttons[buttons.length - 1])

      await user.click(await screen.findByText('Run published version'))
      await user.click(await screen.findByRole('button', { name: /^Run now$/i }))

      expect(await screen.findByText('Set mock output data for Manual Trigger')).toBeInTheDocument()
      expect(executionsFetchClient.POST).not.toHaveBeenCalled()

      await user.click(screen.getByRole('button', { name: /^Run$/i }))

      await waitFor(() => {
        expect(executionsFetchClient.POST).toHaveBeenCalledWith('/executions', {
          body: {
            workflow_id: '1',
            input_data: { version: '' },
            trigger_node_id: 'trigger-1',
            use_published: true,
          },
        })
      })
    })

    it('navigates to executions page filtered by workflow when "View run history" is clicked', async () => {
      routerTestState.navigate.mockClear()

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Wait for table to render (PF Table uses role="grid")
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Find and click the row action button for the first workflow
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Find and click the menu trigger button (the actions menu button)
      // Actions column is always the last column, so the actions button is the last button in the row
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Wait for menu to open and click the "View run history" menu item
      const viewRunHistoryItem = await screen.findByText('View run history')
      await user.click(viewRunHistoryItem)

      // Verify navigation to executions page with workflow filter
      await waitFor(() => {
        expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/executions', search: { workflow_id: '1' } })
      })
    })
  })

  describe('Pagination', () => {
    beforeEach(() => {
      vi.clearAllMocks()
    })

    it('displays pagination controls when next or prev cursors are available', () => {
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor-xyz',
          prev: null,
          total: 30,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Workflows />, { wrapper })

      const nextButton = screen.getByRole('button', { name: 'Go to next page' })
      const prevButton = screen.getByRole('button', { name: 'Go to previous page' })

      expect(nextButton).toBeInTheDocument()
      expect(prevButton).toBeInTheDocument()
      expect(nextButton).not.toBeDisabled()
      expect(prevButton).toBeDisabled()
    })

    it('displays total count when available', () => {
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor',
          prev: null,
          total: 30,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Workflows />, { wrapper })

      // PF Pagination renders items range and total in a toggle (text split across <b> tags)
      const pagination = screen.getByRole('navigation', { name: /pagination/i })
      expect(pagination).toBeInTheDocument()
      expect(screen.getByText('1 - 20')).toBeInTheDocument()
      expect(screen.getByText((content, element) => element?.tagName === 'B' && content === '30')).toBeInTheDocument()
    })

    it('enables both buttons when both cursors are available', async () => {
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor',
          prev: 'prev-cursor-xyz',
          total: 50,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Navigate to page 2 so both prev and next are enabled
      await user.click(screen.getByRole('button', { name: 'Go to next page' }))

      const nextButton = screen.getByRole('button', { name: 'Go to next page' })
      const prevButton = screen.getByRole('button', { name: 'Go to previous page' })

      expect(nextButton).not.toBeDisabled()
      expect(prevButton).not.toBeDisabled()
    })

    it('hides pagination when no cursors are available', () => {
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: null,
          prev: null,
          total: 3,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Workflows />, { wrapper })

      expect(screen.queryByRole('button', { name: 'Next page' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Previous page' })).not.toBeInTheDocument()
    })

    it('handles navigation back to first page correctly', async () => {
      // Start with data that has a next cursor so we can navigate forward
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor',
          prev: null,
          total: 40,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const user = userEvent.setup()
      const { rerender } = render(<Workflows />, { wrapper })

      // Navigate to page 2
      await user.click(screen.getByRole('button', { name: 'Go to next page' }))

      // Now simulate being on last page with only prev cursor available
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: null,
          prev: 'cursor-page1',
          total: 40,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })
      rerender(<Workflows />)

      const prevButton = await screen.findByRole('button', { name: 'Go to previous page' })

      // Previous should be enabled (we're on page 2)
      expect(prevButton).not.toBeDisabled()

      // Clicking previous should work without errors
      await user.click(prevButton)
    })

    it('does not reset cursor while query is fetching', async () => {
      // Mock initial state with data and next cursor
      const mockRefetch = vi.fn()
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor',
          prev: null,
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Verify pagination controls present
      const nextButton = screen.getByRole('button', { name: 'Go to next page' })
      expect(nextButton).toBeInTheDocument()

      // Click Next to set internal cursor state
      await user.click(nextButton)

      // Now simulate fetching state (cursor should NOT be reset while isFetching)
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor',
          prev: 'prev-cursor',
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: true, // Fetching prevents cursor reset
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      // Force re-render to trigger useEffect with new query state
      await user.click(nextButton)

      // Verify pagination controls still present (cursor was not reset despite empty data)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Go to next page' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Go to previous page' })).toBeInTheDocument()
      })
    })

    it('resets cursor when data is empty and query is not fetching', async () => {
      const mockRefetch = vi.fn()

      // Start with data
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: 'next-cursor',
          prev: null,
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      const { rerender } = render(<Workflows />, { wrapper })

      // Simulate truly empty state - no data and not fetching
      mockWorkflowQuery({
        data: {
          resources: [],
          next: null,
          prev: null,
          total: 0,
        },
        isPending: false,
        isLoading: false,
        isFetching: false, // Not fetching allows cursor reset
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      rerender(<Workflows />)

      // Should show empty state (cursor was reset)
      await waitFor(() => {
        expect(screen.getByText('No workflows yet')).toBeInTheDocument()
      })
    })
  })

  describe('Delete Workflow', () => {
    it('shows delete option in row actions menu', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      // Wait for table to render
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Open the actions menu
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Verify delete option exists
      await waitFor(() => {
        expect(screen.getByText('Delete workflow')).toBeInTheDocument()
      })
    })

    it('opens delete confirmation dialog when delete is clicked', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      // Open actions menu
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      // Click delete
      const deleteItem = await screen.findByText('Delete workflow')
      await user.click(deleteItem)

      // Verify modal is shown
      await waitFor(() => {
        expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
        expect(
          screen.getByText(
            /will be deleted and any in-progress runs will stop immediately. This action cannot be undone/
          )
        ).toBeInTheDocument()
      })
    })

    it('deletes workflow successfully and shows success alert', async () => {
      const mockRefetch = vi.fn()
      const mockDeleteMutate = vi.fn(
        (
          params: unknown,
          callbacks?: { onSuccess?: (...args: unknown[]) => void; onError?: (...args: unknown[]) => void }
        ) => {
          if (callbacks?.onSuccess) {
            callbacks.onSuccess(undefined, params, undefined)
          }
        }
      )

      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: null,
          prev: null,
          total: mockWorkflows.length,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      vi.mocked(workflowClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle',
        submittedAt: 0,
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Open actions menu and click delete
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const deleteItem = await screen.findByText('Delete workflow')
      await user.click(deleteItem)

      // Confirm deletion
      await waitFor(() => {
        expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('checkbox', { name: /I understand this workflow/ }))
      const deleteButton = screen.getByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // Verify success
      await waitFor(() => {
        expect(mockDeleteMutate).toHaveBeenCalled()
        expect(mockRefetch).toHaveBeenCalled()
        expect(screen.getByText('Workflow deleted')).toBeInTheDocument()
        expect(screen.getByText(/Successfully deleted workflow/)).toBeInTheDocument()
      })
    })

    it('handles delete error and shows error alert', async () => {
      const mockError = { message: 'Delete failed' }
      const mockDeleteMutate = vi.fn(
        (
          params: unknown,
          callbacks?: { onSuccess?: (...args: unknown[]) => void; onError?: (...args: unknown[]) => void }
        ) => {
          if (callbacks?.onError) {
            callbacks.onError(mockError, params, undefined)
          }
        }
      )

      vi.mocked(workflowClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle',
        submittedAt: 0,
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Open actions menu and click delete
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const deleteItem = await screen.findByText('Delete workflow')
      await user.click(deleteItem)

      // Confirm deletion
      await waitFor(() => {
        expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('checkbox', { name: /I understand this workflow/ }))
      const deleteButton = screen.getByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // Verify error alert
      await waitFor(() => {
        expect(mockDeleteMutate).toHaveBeenCalled()
        expect(screen.getByText('Delete failed')).toBeInTheDocument()
        expect(screen.getByText(/Failed to delete workflow/)).toBeInTheDocument()
      })
    })

    it('can cancel delete operation', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Open actions menu and click delete
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const deleteItem = await screen.findByText('Delete workflow')
      await user.click(deleteItem)

      // Modal appears
      await waitFor(() => {
        expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
      })

      // Click cancel
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      await user.click(cancelButton)

      // Modal closes
      await waitFor(() => {
        expect(screen.queryByText('Delete workflow?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Empty States', () => {
    it('shows EmptyStateNoData when no workflows and no active filters', () => {
      mockWorkflowQuery({
        data: {
          resources: [],
          next: null,
          prev: null,
          total: 0,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
        isFetching: false,
      })

      render(<Workflows />, { wrapper })

      expect(screen.getByText('No workflows yet')).toBeInTheDocument()
      expect(screen.getByText('Create your first workflow to get started.')).toBeInTheDocument()
      expect(screen.queryByRole('search', { name: 'Filters' })).not.toBeInTheDocument()
      // Import workflow is visible even with 0 workflows when a project is selected —
      // the button is always shown for any specific project so users can import into it.
      expect(screen.getByRole('button', { name: 'Import workflow' })).toBeInTheDocument()
      // Create workflow only appears in the empty state body, not the toolbar (toolbar
      // hides Create when there are no workflows and no active filters).
      const createButtons = screen.getAllByRole('button', { name: 'Create workflow' })
      expect(createButtons).toHaveLength(1)
    })

    it('navigates to builder when empty state "Create workflow" button is clicked', async () => {
      const user = userEvent.setup()
      routerTestState.navigate.mockClear()

      mockWorkflowQuery({
        data: {
          resources: [],
          next: null,
          prev: null,
          total: 0,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
        isFetching: false,
      })

      render(<Workflows />, { wrapper })

      const createButton = screen.getByRole('button', { name: 'Create workflow' })
      await user.click(createButton)

      expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflow-builder/new' })
    })

    it('shows EmptyStateFilter when active filters return no results', () => {
      // Set up URL to have an active filter
      mockSearchParams = new URLSearchParams('name%5Bcontains%5D=nonexistent')

      mockWorkflowQuery({
        data: {
          resources: [],
          next: null,
          prev: null,
          total: 0,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
        isFetching: false,
      })

      render(<Workflows />, { wrapper })

      // Should show EmptyStateFilter (not EmptyStateNoData) because filters are active
      expect(screen.getByText('No results found')).toBeInTheDocument()
    })
  })

  describe('Run workflow with navigation', () => {
    it('navigates to execution detail page on successful run when response has id', async () => {
      routerTestState.navigate.mockClear()
      vi.mocked(executionsFetchClient.POST).mockResolvedValue({
        data: { id: 'exec-123' },
        error: undefined,
      } as never)

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Open actions menu and click "Run workflow"
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const runItem = await screen.findByText('Run published version')
      await user.click(runItem)

      const runButton = await screen.findByRole('button', { name: /^Run now$/i })
      await user.click(runButton)

      await waitFor(() => {
        expect(routerTestState.navigate).toHaveBeenCalledWith({
          to: '/executions/exec-123',
        })
      })
    })
  })

  describe('Delete workflow settled behavior', () => {
    it('closes dialog and clears workflow on settled (success)', async () => {
      const mockDeleteMutate = vi.fn(
        (
          params: unknown,
          callbacks?: {
            onSuccess?: (...args: unknown[]) => void
            onError?: (...args: unknown[]) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onSuccess?.(undefined, params, undefined)
          callbacks?.onSettled?.()
        }
      )

      vi.mocked(workflowClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle',
        submittedAt: 0,
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Open actions menu and click delete
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const deleteItem = await screen.findByText('Delete workflow')
      await user.click(deleteItem)

      await waitFor(() => {
        expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('checkbox', { name: /I understand this workflow/ }))
      const deleteButton = screen.getByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // After onSettled, the delete dialog should be closed
      await waitFor(() => {
        expect(screen.queryByText('Delete workflow?')).not.toBeInTheDocument()
      })
    })

    it('closes dialog and clears workflow on settled (error)', async () => {
      const mockDeleteMutate = vi.fn(
        (
          params: unknown,
          callbacks?: {
            onSuccess?: (...args: unknown[]) => void
            onError?: (...args: unknown[]) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onError?.(new Error('fail'), params, undefined)
          callbacks?.onSettled?.()
        }
      )

      vi.mocked(workflowClient.useMutation).mockReturnValue({
        mutate: mockDeleteMutate,
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle',
        submittedAt: 0,
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const deleteItem = await screen.findByText('Delete workflow')
      await user.click(deleteItem)

      await waitFor(() => {
        expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('checkbox', { name: /I understand this workflow/ }))
      const deleteButton = screen.getByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // After onSettled, the delete dialog should be closed even on error
      await waitFor(() => {
        expect(screen.queryByText('Delete workflow?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Grouped view (All Projects)', () => {
    it('renders grouped workflows when all projects are selected', () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [
          { id: 'proj-1', name: 'Project Alpha' },
          { id: 'proj-2', name: 'Project Beta' },
        ],
        ProjectSelector: null,
      })

      const workflowsWithProjects = [
        {
          id: '1',
          name: 'Workflow A',
          description: '',
          created_at: '2023-01-01T00:00:00Z',
          updated_at: '2023-01-02T00:00:00Z',
          is_enabled: true,
          labels: {},
          project_id: 'proj-1',
        },
        {
          id: '2',
          name: 'Workflow B',
          description: '',
          created_at: '2023-02-01T00:00:00Z',
          updated_at: '2023-02-02T00:00:00Z',
          is_enabled: false,
          labels: {},
          project_id: 'proj-2',
        },
      ]

      mockWorkflowQuery({
        data: {
          resources: workflowsWithProjects,
          next: null,
          prev: null,
          total: 2,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Workflows />, { wrapper })

      // Grouped view shows project names as group headers
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      expect(screen.getByText('Project Beta')).toBeInTheDocument()

      // Count badge removed — page-local counts were misleading (AAP-85112)
      const alphaHeader = screen.getByRole('row', { name: /Project Alpha/ })
      expect(within(alphaHeader).queryByText('1')).not.toBeInTheDocument()

      // Workflows should still be rendered
      expect(screen.getByText('Workflow A')).toBeInTheDocument()
      expect(screen.getByText('Workflow B')).toBeInTheDocument()
    })

    it('toggles project group collapsed/expanded', async () => {
      const user = userEvent.setup()

      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        isAllProjects: true,
        projects: [{ id: 'proj-1', name: 'Project Alpha' }],
        ProjectSelector: null,
      })

      const workflowsWithProjects = [
        {
          id: '1',
          name: 'Workflow A',
          description: '',
          created_at: '2023-01-01T00:00:00Z',
          updated_at: '2023-01-02T00:00:00Z',
          is_enabled: true,
          labels: {},
          project_id: 'proj-1',
        },
      ]

      mockWorkflowQuery({
        data: {
          resources: workflowsWithProjects,
          next: null,
          prev: null,
          total: 1,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Workflows />, { wrapper })

      // Project group header should be visible
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      // Workflow should be visible (expanded by default)
      expect(screen.getByText('Workflow A')).toBeInTheDocument()

      // Click the project group header to collapse
      await user.click(screen.getByText('Project Alpha'))

      // Workflow should be hidden (collapsed)
      expect(screen.queryByText('Workflow A')).not.toBeInTheDocument()

      // Click again to expand
      await user.click(screen.getByText('Project Alpha'))

      // Workflow should be visible again
      expect(screen.getByText('Workflow A')).toBeInTheDocument()
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

      render(<Workflows />, { wrapper })

      // Query is called with cursor pagination params
      expect(workflowClient.useQuery).toHaveBeenCalledWith(
        'get',
        '/workflows',
        expect.objectContaining({
          params: {
            query: expect.objectContaining({
              limit: 20,
              include_total: true,
            }) as unknown,
          },
        }) as unknown,
        expect.objectContaining({ enabled: false }) as unknown
      )
    })
  })

  describe('Singular/plural workflow count', () => {
    it('shows singular "workflow" for exactly one result', () => {
      const singleResult = {
        data: {
          resources: [mockWorkflows[0]],
          next: null,
          prev: null,
          total: 1,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }
      mockWorkflowQuery(singleResult)

      render(<Workflows />, { wrapper })

      // PF Pagination renders items range in <b> tags: "<b>1 - 1</b> of <b>1</b> items"
      expect(screen.getByText('1 - 1')).toBeInTheDocument()
    })
  })

  describe('Duplicate Workflow Row Action', () => {
    beforeEach(() => {
      vi.mocked(workflowFetchClient.GET).mockReset()
      vi.mocked(workflowFetchClient.POST).mockReset()
    })

    // workflowFetchClient is overloaded across paths so partial mock data
    // can't satisfy the union. Centralize the cast here instead of scattering
    // `as never` across every mock call.
    function mockGetResponse(data: Record<string, unknown> | undefined, error?: Record<string, unknown>) {
      return { data, error, response: new Response() } as never
    }

    function mockPostResponse(data: Record<string, unknown> | undefined, error?: Record<string, unknown>) {
      return { data, error, response: new Response() } as never
    }

    const openKebabMenuForFirstRow = async (user: ReturnType<typeof userEvent.setup>) => {
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)
    }

    it('uses fallback values for missing workflow fields', async () => {
      const user = userEvent.setup()
      const minimalWorkflows = [{ ...mockWorkflows[0], name: undefined, description: undefined, labels: undefined }]
      mockWorkflowQuery({
        data: { resources: minimalWorkflows, next: null, prev: null, total: 1 },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn().mockResolvedValue(undefined),
      })

      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          version: {
            workflow_definition: { schema_version: '2.0.0', triggers: [], nodes: [], edges: [] },
          },
        })
      )
      vi.mocked(workflowFetchClient.POST).mockResolvedValue(
        mockPostResponse({ id: 'new-id', name: 'test', created_by: 'user-1' })
      )

      await openKebabMenuForFirstRow(user)
      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        const postCall = vi.mocked(workflowFetchClient.POST).mock.calls[0]
        const body = (postCall[1] as { body: { name: string; description: string } }).body
        expect(body.name).toMatch(/^workflow - duplicate-/)
        expect(body.description).toBe('')
      })
    })

    it('shows "Duplicate workflow" in the kebab menu', async () => {
      const user = userEvent.setup()
      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      expect(duplicateItem).toBeInTheDocument()
    })

    it('duplicates workflow successfully and shows success alert', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn().mockResolvedValue(undefined)
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: null,
          prev: null,
          total: mockWorkflows.length,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          name: 'Important Project Workflow',
          version: {
            workflow_definition: {
              schema_version: '2.0.0',
              triggers: [],
              nodes: [],
              edges: [],
            },
          },
        })
      )

      vi.mocked(workflowFetchClient.POST).mockResolvedValue(
        mockPostResponse({ id: 'new-id', name: 'Important Project Workflow - duplicate-abc', created_by: 'user-1' })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(workflowFetchClient.GET).toHaveBeenCalledWith('/workflows/{workflow_id}', {
          params: { path: { workflow_id: '1' } },
        })
      })

      await waitFor(() => {
        expect(workflowFetchClient.POST).toHaveBeenCalledWith(
          '/workflows',
          expect.objectContaining({
            body: expect.objectContaining({
              workflow_definition: expect.objectContaining({
                schema_version: '2.0.0',
              }) as unknown,
            }) as unknown,
          }) as unknown
        )
      })

      await waitFor(() => {
        expect(screen.getByText('Workflow duplicated')).toBeInTheDocument()
      })

      expect(screen.getByText(/^Created ".+ - duplicate-/)).toBeInTheDocument()
    })

    it('shows error alert when fetching workflow fails', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse(undefined, {
          type: 'https://api.example.com/errors/workflow-not-found',
          title: 'Workflow Not Found',
          detail: 'Workflow not found',
          code: 'WORKFLOW_NOT_FOUND',
          retryable: false,
        })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(screen.getByText('Duplicate failed')).toBeInTheDocument()
      })
    })

    it('shows error alert when creating duplicate fails', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          name: 'Important Project Workflow',
          version: {
            workflow_definition: {
              schema_version: '2.0.0',
              triggers: [],
              nodes: [],
              edges: [],
            },
          },
        })
      )

      vi.mocked(workflowFetchClient.POST).mockResolvedValue(
        mockPostResponse(undefined, {
          type: 'https://api.example.com/errors/name-conflict',
          title: 'Workflow Name Conflict',
          detail: 'Name conflict',
          code: 'WORKFLOW_NAME_CONFLICT',
          retryable: false,
        })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(screen.getByText('Duplicate failed')).toBeInTheDocument()
      })
    })

    it('generates a name with duplicate suffix', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          name: 'Important Project Workflow',
          version: {
            workflow_definition: {
              schema_version: '2.0.0',
              triggers: [],
              nodes: [],
              edges: [],
            },
          },
        })
      )

      vi.mocked(workflowFetchClient.POST).mockResolvedValue(
        mockPostResponse({ id: 'new-id', name: 'test', created_by: 'user-1' })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        const postCall = vi.mocked(workflowFetchClient.POST).mock.calls[0]
        const body = (postCall[1] as { body: { name: string } }).body
        expect(body.name).toMatch(/^Important Project Workflow - duplicate-[a-z\d]+$/)
      })
    })

    it('creates duplicate with workflow definition', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          name: 'Important Project Workflow',
          version: {
            workflow_definition: {
              schema_version: '2.0.0',
              triggers: [],
              nodes: [],
              edges: [],
            },
          },
        })
      )

      vi.mocked(workflowFetchClient.POST).mockResolvedValue(
        mockPostResponse({ id: 'new-id', name: 'test', created_by: 'user-1' })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        const postCall = vi.mocked(workflowFetchClient.POST).mock.calls[0]
        const body = (postCall[1] as { body: { workflow_definition: object } }).body
        expect(body.workflow_definition).toBeDefined()
      })
    })

    it('shows no action link when response has no id', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          name: 'Important Project Workflow',
          version: {
            workflow_definition: {
              schema_version: '2.0.0',
              triggers: [],
              nodes: [],
              edges: [],
            },
          },
        })
      )

      vi.mocked(workflowFetchClient.POST).mockResolvedValue(mockPostResponse({ name: 'test', created_by: 'user-1' }))

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(screen.getByText('Workflow duplicated')).toBeInTheDocument()
        expect(screen.getByText(/^Created ".+ - duplicate-/)).toBeInTheDocument()
      })
      expect(screen.queryByRole('button', { name: 'Open workflow' })).not.toBeInTheDocument()
    })

    it('shows error when GET returns no data', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(mockGetResponse(undefined))

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(screen.getByText('Duplicate failed')).toBeInTheDocument()
      })
    })

    it('shows error when fetch throws an unexpected error', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockRejectedValue(new Error('Network error'))

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(screen.getByText('Duplicate failed')).toBeInTheDocument()
      })
    })

    it('shows error when workflow has no definition', async () => {
      const user = userEvent.setup()
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          name: 'Important Project Workflow',
          version: {},
        })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(screen.getByText('Duplicate failed')).toBeInTheDocument()
        expect(screen.getByText('Workflow has no definition to duplicate')).toBeInTheDocument()
      })
    })

    it('shows error when workflow has no project_id', async () => {
      const user = userEvent.setup()
      const workflowWithoutProject = [{ ...mockWorkflows[0], project_id: undefined }]
      mockWorkflowQuery({
        data: { resources: workflowWithoutProject, next: null, prev: null, total: 1 },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn().mockResolvedValue(undefined),
      })

      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          version: {
            workflow_definition: { schema_version: '2.0.0', triggers: [], nodes: [], edges: [] },
          },
        })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      await waitFor(() => {
        expect(screen.getByText('Duplicate failed')).toBeInTheDocument()
        expect(screen.getByText('Workflow must have a project ID')).toBeInTheDocument()
      })
    })

    it('transforms approval node approvers from objects to strings when duplicating', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn().mockResolvedValue(undefined)
      mockWorkflowQuery({
        data: {
          resources: mockWorkflows,
          next: null,
          prev: null,
          total: mockWorkflows.length,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      // Mock GET to return workflow with approval node containing user/group objects
      vi.mocked(workflowFetchClient.GET).mockResolvedValue(
        mockGetResponse({
          id: '1',
          name: 'Workflow with Approval',
          version: {
            workflow_definition: {
              schema_version: '2.0.0',
              triggers: [],
              nodes: [
                {
                  id: 'approval-1',
                  type: 'approval',
                  name: 'Approval Node',
                  config: {
                    approver_users: [
                      { id: 'user-1', username: 'alice' },
                      { id: 'user-2', username: 'bob' },
                    ],
                    approver_groups: [
                      { id: 'group-1', name: 'admins' },
                      { id: 'group-2', name: 'reviewers' },
                    ],
                  },
                },
              ],
              edges: [],
            },
          },
        })
      )

      vi.mocked(workflowFetchClient.POST).mockResolvedValue(
        mockPostResponse({ id: 'new-id', name: 'Workflow with Approval - duplicate-abc', created_by: 'user-1' })
      )

      await openKebabMenuForFirstRow(user)

      const duplicateItem = await screen.findByText('Duplicate workflow')
      await user.click(duplicateItem)

      // Verify the POST call transformed approver objects to string arrays
      await waitFor(() => {
        expect(workflowFetchClient.POST).toHaveBeenCalledWith(
          '/workflows',
          expect.objectContaining({
            body: expect.objectContaining({
              workflow_definition: expect.objectContaining({
                nodes: [
                  expect.objectContaining({
                    id: 'approval-1',
                    type: 'approval',
                    config: expect.objectContaining({
                      approver_users: ['alice', 'bob'],
                      approver_groups: ['admins', 'reviewers'],
                    }) as unknown,
                  }),
                ],
              }) as unknown,
            }) as unknown,
          }) as unknown
        )
      })

      await waitFor(() => {
        expect(screen.getByText('Workflow duplicated')).toBeInTheDocument()
      })
    })
  })

  describe('Publish Workflow', () => {
    it('shows publish option in row actions menu', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      await waitFor(() => {
        expect(screen.getByText('Publish workflow')).toBeInTheDocument()
      })
    })

    it('opens publish dialog when publish is clicked', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const publishItem = await screen.findByText('Publish workflow')
      await user.click(publishItem)

      await waitFor(() => {
        expect(screen.getByText('Publish workflow?')).toBeInTheDocument()
      })
    })

    it('does not show unpublish option for unpublished workflows', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const secondDataRow = rows[2]

      const buttons = within(secondDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      await waitFor(() => {
        expect(screen.getByText('Publish workflow')).toBeInTheDocument()
        expect(screen.queryByText('Unpublish workflow')).not.toBeInTheDocument()
      })
    })
  })

  describe('Publish Workflow Mutation', () => {
    const workflowWithVersion = {
      ...mockWorkflows[0],
      current_version: 5,
    }

    const openPublishDialogForFirstRow = async (user: ReturnType<typeof userEvent.setup>) => {
      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const publishItem = await screen.findByText('Publish workflow')
      await user.click(publishItem)

      await waitFor(() => {
        expect(screen.getByText('Publish workflow?')).toBeInTheDocument()
      })
    }

    it('publishes workflow successfully and shows success alert', async () => {
      const mockRefetch = vi.fn()
      const mockPublishMutate = vi.fn(
        (
          _params: unknown,
          callbacks?: {
            onSuccess?: () => void
            onError?: (error: unknown) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onSuccess?.()
          callbacks?.onSettled?.()
        }
      )

      mockWorkflowQuery({
        data: {
          resources: [workflowWithVersion],
          next: null,
          prev: null,
          total: 1,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      const defaultMutationReturn = {
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle' as const,
        submittedAt: 0,
      }

      vi.mocked(workflowClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/publish')) {
          return { ...defaultMutationReturn, mutate: mockPublishMutate } as never
        }
        return { ...defaultMutationReturn, mutate: vi.fn() } as never
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })
      await openPublishDialogForFirstRow(user)

      // Fill form and submit
      const publishButton = screen.getByRole('button', { name: 'Publish' })
      await user.click(publishButton)

      await waitFor(() => {
        expect(mockPublishMutate).toHaveBeenCalled()
      })

      await waitFor(() => {
        expect(screen.getByText('Workflow published successfully')).toBeInTheDocument()
      })
    })

    it('shows error alert when publish fails', async () => {
      const mockPublishMutate = vi.fn(
        (
          _params: unknown,
          callbacks?: {
            onSuccess?: () => void
            onError?: (error: unknown) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onError?.(new Error('Version conflict'))
          callbacks?.onSettled?.()
        }
      )

      mockWorkflowQuery({
        data: {
          resources: [workflowWithVersion],
          next: null,
          prev: null,
          total: 1,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const defaultMutationReturn = {
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle' as const,
        submittedAt: 0,
      }

      vi.mocked(workflowClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/publish')) {
          return { ...defaultMutationReturn, mutate: mockPublishMutate } as never
        }
        return { ...defaultMutationReturn, mutate: vi.fn() } as never
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })
      await openPublishDialogForFirstRow(user)

      const publishButton = screen.getByRole('button', { name: 'Publish' })
      await user.click(publishButton)

      await waitFor(() => {
        expect(screen.getByText('Failed to publish workflow')).toBeInTheDocument()
      })
    })

    it('closes publish dialog on settled', async () => {
      const mockPublishMutate = vi.fn(
        (
          _params: unknown,
          callbacks?: {
            onSuccess?: () => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onSuccess?.()
          callbacks?.onSettled?.()
        }
      )

      mockWorkflowQuery({
        data: {
          resources: [workflowWithVersion],
          next: null,
          prev: null,
          total: 1,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const defaultMutationReturn = {
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle' as const,
        submittedAt: 0,
      }

      vi.mocked(workflowClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/publish')) {
          return { ...defaultMutationReturn, mutate: mockPublishMutate } as never
        }
        return { ...defaultMutationReturn, mutate: vi.fn() } as never
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })
      await openPublishDialogForFirstRow(user)

      const publishButton = screen.getByRole('button', { name: 'Publish' })
      await user.click(publishButton)

      // Dialog should close after settled
      await waitFor(() => {
        expect(screen.queryByText('Publish workflow?')).not.toBeInTheDocument()
      })
    })
  })

  describe('Unpublish Workflow', () => {
    const publishedWorkflows = [
      {
        ...mockWorkflows[0],
        published_version_id: 'ver-3',
      },
      {
        ...mockWorkflows[1],
        published_version_id: null,
      },
    ]

    it('shows unpublish option for published workflows in row actions menu', async () => {
      mockWorkflowQuery({
        data: {
          resources: publishedWorkflows,
          next: null,
          prev: null,
          total: 2,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      // Open actions menu for the first workflow (published)
      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      await waitFor(() => {
        expect(screen.getByText('Unpublish workflow')).toBeInTheDocument()
      })
    })

    it('opens unpublish confirmation dialog when unpublish is clicked', async () => {
      mockWorkflowQuery({
        data: {
          resources: publishedWorkflows,
          next: null,
          prev: null,
          total: 2,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const unpublishItem = await screen.findByText('Unpublish workflow')
      await user.click(unpublishItem)

      await waitFor(() => {
        expect(screen.getByText('Unpublish workflow?')).toBeInTheDocument()
        expect(screen.getByText(/will be unpublished/)).toBeInTheDocument()
      })
    })

    it('unpublishes workflow successfully and shows success alert', async () => {
      const mockRefetch = vi.fn()
      const mockUnpublishMutate = vi.fn(
        (
          _params: unknown,
          callbacks?: {
            onSuccess?: () => void
            onError?: (error: unknown) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onSuccess?.()
          callbacks?.onSettled?.()
        }
      )

      mockWorkflowQuery({
        data: {
          resources: publishedWorkflows,
          next: null,
          prev: null,
          total: 2,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      const defaultMutationReturn = {
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle' as const,
        submittedAt: 0,
      }

      vi.mocked(workflowClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/unpublish')) {
          return { ...defaultMutationReturn, mutate: mockUnpublishMutate } as never
        }
        return { ...defaultMutationReturn, mutate: vi.fn() } as never
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const unpublishItem = await screen.findByText('Unpublish workflow')
      await user.click(unpublishItem)

      await waitFor(() => {
        expect(screen.getByText('Unpublish workflow?')).toBeInTheDocument()
      })

      const unpublishButton = screen.getByRole('button', { name: 'Unpublish' })
      await user.click(unpublishButton)

      await waitFor(() => {
        expect(mockUnpublishMutate).toHaveBeenCalled()
        expect(screen.getByText('Workflow unpublished successfully')).toBeInTheDocument()
      })
    })

    it('shows error alert when unpublish fails', async () => {
      const mockUnpublishMutate = vi.fn(
        (
          _params: unknown,
          callbacks?: {
            onSuccess?: () => void
            onError?: (error: unknown) => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onError?.(new Error('Cannot unpublish'))
          callbacks?.onSettled?.()
        }
      )

      mockWorkflowQuery({
        data: {
          resources: publishedWorkflows,
          next: null,
          prev: null,
          total: 2,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const defaultMutationReturn = {
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle' as const,
        submittedAt: 0,
      }

      vi.mocked(workflowClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/unpublish')) {
          return { ...defaultMutationReturn, mutate: mockUnpublishMutate } as never
        }
        return { ...defaultMutationReturn, mutate: vi.fn() } as never
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const unpublishItem = await screen.findByText('Unpublish workflow')
      await user.click(unpublishItem)

      await waitFor(() => {
        expect(screen.getByText('Unpublish workflow?')).toBeInTheDocument()
      })

      const unpublishButton = screen.getByRole('button', { name: 'Unpublish' })
      await user.click(unpublishButton)

      await waitFor(() => {
        expect(screen.getByText('Failed to unpublish workflow')).toBeInTheDocument()
      })
    })

    it('closes unpublish dialog on settled', async () => {
      const mockUnpublishMutate = vi.fn(
        (
          _params: unknown,
          callbacks?: {
            onSuccess?: () => void
            onSettled?: () => void
          }
        ) => {
          callbacks?.onSuccess?.()
          callbacks?.onSettled?.()
        }
      )

      mockWorkflowQuery({
        data: {
          resources: publishedWorkflows,
          next: null,
          prev: null,
          total: 2,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      const defaultMutationReturn = {
        mutateAsync: vi.fn(),
        reset: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        isIdle: true,
        error: null,
        data: undefined,
        variables: undefined,
        context: undefined,
        failureCount: 0,
        failureReason: null,
        status: 'idle' as const,
        submittedAt: 0,
      }

      vi.mocked(workflowClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/unpublish')) {
          return { ...defaultMutationReturn, mutate: mockUnpublishMutate } as never
        }
        return { ...defaultMutationReturn, mutate: vi.fn() } as never
      })

      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]
      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const unpublishItem = await screen.findByText('Unpublish workflow')
      await user.click(unpublishItem)

      await waitFor(() => {
        expect(screen.getByText('Unpublish workflow?')).toBeInTheDocument()
      })

      const unpublishButton = screen.getByRole('button', { name: 'Unpublish' })
      await user.click(unpublishButton)

      await waitFor(() => {
        expect(screen.queryByText('Unpublish workflow?')).not.toBeInTheDocument()
      })
    })
  })

  describe('API sorting', () => {
    beforeEach(() => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: { id: 'proj-default', name: 'Default Project' },
        selectedProjectId: 'proj-default',
        stableProjectId: 'proj-default',
        isAllProjects: false,
        projects: [{ id: 'proj-default', name: 'Default Project' }],
        ProjectSelector: null,
        refetchProjects: vi.fn(),
      } as never)
    })

    it('defaults query sort to -updated_at', () => {
      render(<Workflows />, { wrapper })

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

    it('excludes built-in workflows from all-projects queries so page size matches the table', () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: null,
        selectedProjectId: undefined,
        stableProjectId: undefined,
        isAllProjects: true,
        projects: [{ id: 'proj-default', name: 'Default Project', is_builtin: false }],
        ProjectSelector: null,
        refetchProjects: vi.fn(),
      } as never)

      render(<Workflows />, { wrapper })

      expect(workflowClient.useQuery).toHaveBeenCalledWith(
        'get',
        '/workflows',
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({
              is_builtin: false,
              sort: '-updated_at',
            }) as unknown,
          }) as unknown,
        }) as unknown,
        expect.objectContaining({ enabled: true }) as unknown
      )
    })

    it('renders sortable headers for name, created, updated, and state', () => {
      render(<Workflows />, { wrapper })

      for (const name of [/Name/i, /Created at/i, /Updated at/i, /^State$/i]) {
        const header = screen.getByRole('columnheader', { name })
        expect(within(header).getByRole('button')).toBeInTheDocument()
      }

      const actionsHeader = screen.getByRole('columnheader', { name: 'Actions' })
      expect(within(actionsHeader).queryByRole('button')).not.toBeInTheDocument()
    })

    it('writes sort URL param when a column header is clicked', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /Name/i })
      await user.click(within(nameHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'name')
      })
    })

    it('can sort by is_enabled via the State column', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      const stateHeader = screen.getByRole('columnheader', { name: /^State$/i })
      await user.click(within(stateHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'is_enabled')
      })
    })
  })

  describe('builtin project protection', () => {
    beforeEach(() => {
      // Row builtin checks use selectedProject / grouping projects (not a standalone
      // useAllProjects lookup). Select the builtin project that owns mockWorkflows[0].
      mockUseProjectSelector.mockReturnValue({
        selectedProject: { id: 'project-1', name: 'Project 1', is_builtin: true },
        selectedProjectId: 'project-1',
        stableProjectId: 'project-1',
        isAllProjects: false,
        projects: [{ id: 'project-1', name: 'Project 1', is_builtin: true }],
        ProjectSelector: null,
        refetchProjects: vi.fn(),
      } as never)
    })

    it('disables edit row action for workflows in a builtin project', async () => {
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const editItem = await screen.findByRole('menuitem', { name: /Edit workflow/ })
      expect(editItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables edit row action even when canUpdate is false', async () => {
      mockWorkflowPermissions.current = { ...mockWorkflowPermissions.current, canUpdate: false }
      const user = userEvent.setup()
      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const table = screen.getByRole('grid', { name: 'Workflows table' })
      const rows = within(table).getAllByRole('row')
      const firstDataRow = rows[1]

      const buttons = within(firstDataRow).getAllByRole('button')
      const menuTrigger = buttons[buttons.length - 1]
      await user.click(menuTrigger)

      const editItem = await screen.findByRole('menuitem', { name: /Edit workflow/ })
      expect(editItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables Create workflow button when selected project is builtin', async () => {
      mockUseProjectSelector.mockReturnValue({
        selectedProject: { id: 'project-1', name: 'Builtin Project', is_builtin: true } as never,
        isAllProjects: false,
        projects: [{ id: 'project-1', name: 'Builtin Project', is_builtin: true }] as never,
        ProjectSelector: null,
      })

      render(<Workflows />, { wrapper })

      await waitFor(() => {
        expect(screen.getByRole('grid', { name: 'Workflows table' })).toBeInTheDocument()
      })

      const createBtn = screen.getByRole('button', { name: 'Create workflow' })
      expect(createBtn).toHaveAttribute('aria-disabled', 'true')
    })
  })
})
