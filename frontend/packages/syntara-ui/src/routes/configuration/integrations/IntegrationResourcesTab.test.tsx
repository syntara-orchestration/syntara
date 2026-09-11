import type { Tool } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'

import { IntegrationResourcesTab } from './IntegrationResourcesTab'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useMutation: vi.fn(),
  },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockTools = [
  {
    id: 't1',
    name: 'get_repo',
    description: 'Get a repo',
    enabled: true,
    integration_id: 'int-1',
    namespaced_name: 'int-1/get_repo',
    parameters: [],
    created_by: 'user-1',
  },
  {
    id: 't2',
    name: 'create_pr',
    description: 'Create a PR',
    enabled: true,
    integration_id: 'int-1',
    namespaced_name: 'int-1/create_pr',
    parameters: [],
    created_by: 'user-1',
  },
  {
    id: 't3',
    name: 'list_issues',
    description: 'List issues',
    enabled: false,
    integration_id: 'int-1',
    namespaced_name: 'int-1/list_issues',
    parameters: [],
    created_by: 'user-1',
  },
] as Tool[]

describe('IntegrationResourcesTab', () => {
  const mockRefreshMutate = vi.fn()
  const mockOnRefreshed = vi.fn().mockResolvedValue(undefined)
  const mockRefetchTools = vi.fn().mockResolvedValue(undefined)
  const mockHandleSelectTool = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(integrationsClient.useMutation).mockReturnValue({
      mutateAsync: mockRefreshMutate.mockResolvedValue({}),
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
    })
  })

  function renderTab(overrides?: {
    tools?: typeof mockTools
    enabledToolIds?: Set<string>
    enabledCount?: number
    canUpdate?: boolean
  }) {
    return render(
      <IntegrationResourcesTab
        integrationId="int-1"
        tools={overrides?.tools ?? mockTools}
        enabledToolIds={overrides?.enabledToolIds ?? new Set(['t1', 't2'])}
        enabledCount={overrides?.enabledCount ?? 2}
        handleSelectTool={mockHandleSelectTool}
        lastRefreshedAt="2026-01-01T10:00:00Z"
        canUpdate={overrides?.canUpdate ?? true}
        onRefreshed={mockOnRefreshed}
        refetchTools={mockRefetchTools}
      />,
      { wrapper }
    )
  }

  describe('Rendering', () => {
    it('renders tools in a table with checkboxes', () => {
      renderTab()

      expect(screen.getByText('get_repo')).toBeInTheDocument()
      expect(screen.getByText('create_pr')).toBeInTheDocument()
      expect(screen.getByText('list_issues')).toBeInTheDocument()
    })

    it('shows enabled count', () => {
      renderTab()

      expect(screen.getByText('2 of 3 enabled')).toBeInTheDocument()
    })

    it('shows last refreshed time', () => {
      renderTab()

      expect(screen.getByText(/Last refreshed:/)).toBeInTheDocument()
    })

    it('shows search filter input', () => {
      renderTab()

      expect(screen.getByRole('textbox', { name: /filter tools/i })).toBeInTheDocument()
    })

    it("shows an inline Not found label in the missing tool's row and no Status column", () => {
      const toolsWithMissing = [
        { ...mockTools[0], status: 'available' as const },
        { ...mockTools[1], status: 'missing' as const },
      ] as Tool[]
      renderTab({ tools: toolsWithMissing, enabledToolIds: new Set(['t1', 't2']), enabledCount: 2 })

      // The Status column was replaced by the inline label; guard against it sneaking back.
      expect(screen.queryByRole('columnheader', { name: 'Status' })).not.toBeInTheDocument()

      // The label belongs to the missing tool's own row, not anywhere else on the page.
      const missingRow = screen.getByRole('row', { name: /create_pr/i })
      expect(within(missingRow).getByText('Not found')).toBeInTheDocument()

      const availableRow = screen.getByRole('row', { name: /get_repo/i })
      expect(within(availableRow).queryByText('Not found')).not.toBeInTheDocument()
    })

    it('does not show a Not found label when all tools are available', () => {
      const toolsAllAvailable = mockTools.map((t) => ({ ...t, status: 'available' as const })) as Tool[]
      renderTab({ tools: toolsAllAvailable })

      expect(screen.queryByText('Not found')).not.toBeInTheDocument()
    })

    it('shows a not-found count in the toolbar when tools are missing', () => {
      const toolsWithMissing = [
        { ...mockTools[0], status: 'missing' as const },
        { ...mockTools[1], status: 'missing' as const },
        { ...mockTools[2], status: 'available' as const },
      ] as Tool[]
      renderTab({ tools: toolsWithMissing })

      expect(screen.getByText('2 not found')).toBeInTheDocument()
    })
  })

  describe('Tool selection', () => {
    it('calls handleSelectTool when a tool checkbox is clicked', async () => {
      const user = userEvent.setup()
      renderTab()

      const checkboxes = screen.getAllByRole('checkbox')
      await user.click(checkboxes[1])

      expect(mockHandleSelectTool).toHaveBeenCalled()
    })

    it('select-all checkbox calls handleSelectTool for all filtered tools', async () => {
      const user = userEvent.setup()
      renderTab()

      const selectAllCheckbox = screen.getAllByRole('checkbox')[0]
      await user.click(selectAllCheckbox)

      expect(mockHandleSelectTool).toHaveBeenCalled()
    })
  })

  describe('Refresh', () => {
    it('refreshes directly when refresh button clicked (no confirmation dialog)', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({ refresh_status: 'available', refresh_error: null })

      renderTab()

      await user.click(screen.getByRole('button', { name: 'Refresh resources' }))

      expect(mockRefreshMutate).toHaveBeenCalled()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('shows error toast when refresh returns error status', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({
        refresh_status: 'error',
        refresh_error: 'Connection refused',
      })

      renderTab()

      await user.click(screen.getByRole('button', { name: 'Refresh resources' }))

      await waitFor(() => {
        expect(screen.getByText('Refresh failed')).toBeInTheDocument()
      })
    })

    it('shows success toast when refresh succeeds', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({
        refresh_status: 'available',
        refresh_error: null,
      })

      renderTab()

      await user.click(screen.getByRole('button', { name: 'Refresh resources' }))

      await waitFor(() => {
        expect(screen.getByText('Resources refreshed')).toBeInTheDocument()
      })
    })
  })

  describe('Empty state', () => {
    it('shows empty state when no tools exist', () => {
      renderTab({ tools: [], enabledToolIds: new Set(), enabledCount: 0 })

      expect(screen.getByText('No resources discovered yet')).toBeInTheDocument()
      expect(screen.getByText(/click refresh tools/i)).toBeInTheDocument()
    })
  })

  describe('Permission gating (canUpdate: false)', () => {
    it('disables the refresh button', () => {
      renderTab({ canUpdate: false })
      expect(screen.getByRole('button', { name: 'Refresh resources' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables row checkboxes', () => {
      renderTab({ canUpdate: false })
      const tbody = screen.getAllByRole('rowgroup')[1]
      within(tbody)
        .getAllByRole('checkbox')
        .forEach((cb) => {
          expect(cb).toBeDisabled()
        })
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderTab()

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })

    it('has no accessibility violations with missing tools', async () => {
      const toolsWithMissing = [
        { ...mockTools[0], status: 'available' as const },
        { ...mockTools[1], status: 'missing' as const },
      ] as Tool[]
      const { container } = renderTab({
        tools: toolsWithMissing,
        enabledToolIds: new Set(['t1', 't2']),
        enabledCount: 2,
      })

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })
})
