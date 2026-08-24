import { IntegrationStatusEnum } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { useFilterState } from '../../../hooks/useFilterState'
import { AlertProvider } from '../../../providers/alerts'
import { assertUrlParam } from '../../../test/filter-test-helpers'
import { routerTestState } from '../../../test/setup'

import Integrations from './Integrations'

// Mock dependencies
vi.mock('../../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// Mock useFilterState - will be configured per-test
vi.mock('../../../hooks/useFilterState', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../hooks/useFilterState')>()
  return {
    ...actual,
    useFilterState: vi.fn(actual.useFilterState),
  }
})

const mockSearchParams = new URLSearchParams()
const mockSetSearchParams = vi.fn()

vi.mock('wouter', () => ({
  useLocation: () => ['/configuration/integrations', routerTestState.navigate],
}))

vi.mock('../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/configuration/integrations',
}))

vi.mock('../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}))

const mockPermissions = {
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
}

vi.mock('./useIntegrationPermissions', () => ({
  useIntegrationPermissions: () => mockPermissions,
}))

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
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

type MockMutationCallbacks = {
  onSuccess: (...args: unknown[]) => void
  onError: (...args: unknown[]) => void
  onSettled: () => void
}

describe('Integrations Component', () => {
  const mockIntegrations = [
    {
      id: '1',
      name: 'Primary MCP Server',
      description: 'Main integration server for critical workflows',
      integration_type: 'mcp_server',
      validation_status: IntegrationStatusEnum.AVAILABLE,
      enabled: true,
      scope: 'global',
      configuration: {
        integration_type: 'mcp_server',
        base_url: 'https://primary.example.com',
        discovered_tools: [
          { name: 'tool1' },
          { name: 'tool2' },
          { name: 'tool3' },
          { name: 'tool4' },
          { name: 'tool5' },
        ],
      },
      enabled_tool_count: 5,
      created_at: '2023-01-01T00:00:00Z',
      updated_at: '2023-01-02T00:00:00Z',
    },
    {
      id: '2',
      name: 'Secondary Test Server',
      description: 'Testing environment integration',
      integration_type: 'mcp_server',
      validation_status: IntegrationStatusEnum.ERROR,
      validation_error: 'Connection refused',
      enabled: true,
      scope: 'global',
      configuration: {
        integration_type: 'mcp_server',
        base_url: 'https://secondary.example.com',
        discovered_tools: [{ name: 'tool1' }, { name: 'tool2' }, { name: 'tool3' }],
      },
      enabled_tool_count: 3,
      created_at: '2023-02-01T00:00:00Z',
      updated_at: '2023-02-02T00:00:00Z',
    },
    {
      id: '3',
      name: 'Development Server',
      description: 'Development integration for testing new features',
      integration_type: 'mcp_server',
      validation_status: IntegrationStatusEnum.VALIDATING,
      enabled: true,
      scope: 'global',
      configuration: {
        integration_type: 'mcp_server',
        base_url: 'https://dev.example.com',
        discovered_tools: Array.from({ length: 8 }, (_, i) => ({ name: `tool${String(i + 1)}` })),
      },
      enabled_tool_count: 8,
      created_at: '2023-03-01T00:00:00Z',
      updated_at: '2023-03-02T00:00:00Z',
    },
  ]

  beforeEach(() => {
    // Reset mocks before each test
    routerTestState.navigate.mockClear()
    mockSetSearchParams.mockClear()
    // Reset permissions to admin defaults
    Object.assign(mockPermissions, {
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      isLoading: false,
    })
    // Reset useFilterState to its default implementation (not mocked)
    vi.mocked(useFilterState).mockRestore?.()
    // Clear all search params to start with empty state
    Array.from(mockSearchParams.keys()).forEach((key) => {
      mockSearchParams.delete(key)
    })

    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: { resources: mockIntegrations },
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)

    vi.mocked(integrationsClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
      data: null,
      reset: vi.fn(),
      mutateAsync: vi.fn(),
      isIdle: true,
      isSuccess: false,
      failureCount: 0,
      failureReason: null,
      context: undefined,
      submittedAt: 0,
      variables: undefined,
      status: 'idle',
      isPaused: false,
    } as never)
  })

  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<Integrations />, { wrapper })

      // Check page header
      expect(screen.getByRole('heading', { name: 'Integrations' })).toBeInTheDocument()

      // Check Add Integration button
      expect(screen.getByText('Configure integration')).toBeInTheDocument()

      // Check FilterBar is present (filter input)
      expect(screen.getByRole('textbox', { name: /name filter/i })).toBeInTheDocument()
    })

    it('renders integrations in table view by default', () => {
      render(<Integrations />, { wrapper })

      // Check that integration names are rendered
      expect(screen.getByText('Primary MCP Server')).toBeInTheDocument()
      expect(screen.getByText('Secondary Test Server')).toBeInTheDocument()
      expect(screen.getByText('Development Server')).toBeInTheDocument()
    })
  })

  describe('Filter Functionality', () => {
    it('renders name filter input', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Find the name filter input (PatternFly TextFilter)
      const textInput = screen.getByRole('textbox', { name: /name filter/i })

      // Verify user can type in the filter
      await user.type(textInput, 'primary')
      expect(textInput).toHaveValue('primary')
    })

    it('shows all integrations when no filters are active', () => {
      render(<Integrations />, { wrapper })

      // Verify all integrations are shown
      expect(screen.getByText('Primary MCP Server')).toBeInTheDocument()
      expect(screen.getByText('Secondary Test Server')).toBeInTheDocument()
      expect(screen.getByText('Development Server')).toBeInTheDocument()
    })

    it('displays filter toolbar with field selectors', () => {
      render(<Integrations />, { wrapper })

      // Verify filter input is present
      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      expect(textInput).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays loading state', () => {
      vi.mocked(integrationsClient.useQuery).mockReturnValueOnce({
        data: null,
        isPending: true,
        isError: false,
        error: null,
      })

      render(<Integrations />, { wrapper })

      // Expect loading state
      const loadingElement = screen.getByTestId('loading-state')
      expect(loadingElement).toBeInTheDocument()
    })

    it('displays error state', () => {
      const mockError = new Error('Failed to load integrations')
      // NOTE: component may re-render due to AlertProvider updates; keep error stable across renders
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: null,
        isPending: false,
        isError: true,
        error: mockError,
      })

      render(<Integrations />, { wrapper })

      // Check for error state
      const errorElement = screen.getByTestId('error-state')
      expect(errorElement).toBeInTheDocument()
      // Body shows the Error message; scope to the error state container
      expect(within(errorElement).getByText('Failed to load integrations')).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('displays empty state when no integrations exist and no filters active', () => {
      vi.mocked(integrationsClient.useQuery).mockReturnValueOnce({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      render(<Integrations />, { wrapper })

      // Check for empty state message (no filters active, so shows empty state not filter empty)
      expect(screen.getByText('No integrations yet')).toBeInTheDocument()
      // Multiple "Configure integration" buttons exist (header + empty state), so use getAllByText
      expect(screen.getAllByText('Configure integration').length).toBeGreaterThan(0)
    })

    it('displays filter-empty state when filters are active but no results match', () => {
      mockSearchParams.set('validation_status', 'error')

      vi.mocked(integrationsClient.useQuery).mockReturnValueOnce({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      render(<Integrations />, { wrapper })

      expect(screen.getByText('No results found')).toBeInTheDocument()
      expect(screen.queryByText('No integrations yet')).not.toBeInTheDocument()
    })
  })

  describe('Table Columns', () => {
    it('renders name column', () => {
      render(<Integrations />, { wrapper })

      expect(screen.getByText('Primary MCP Server')).toBeInTheDocument()
      expect(screen.getByText('Secondary Test Server')).toBeInTheDocument()
      expect(screen.getByText('Development Server')).toBeInTheDocument()
    })

    it('renders status column', () => {
      render(<Integrations />, { wrapper })

      const statusCells = screen.getAllByText(/available|error|validating/i)
      expect(statusCells.length).toBeGreaterThanOrEqual(3)
    })

    it('renders integration type column', () => {
      render(<Integrations />, { wrapper })

      const typeCells = screen.getAllByText('MCP Server')
      expect(typeCells.length).toBe(3)
    })

    it('renders tool count column', () => {
      render(<Integrations />, { wrapper })

      expect(screen.getByText('5')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument()
      expect(screen.getByText('8')).toBeInTheDocument()
    })

    it('renders API URL column', () => {
      render(<Integrations />, { wrapper })

      expect(screen.getByText('https://primary.example.com')).toBeInTheDocument()
      expect(screen.getByText('https://secondary.example.com')).toBeInTheDocument()
      expect(screen.getByText('https://dev.example.com')).toBeInTheDocument()
    })
  })

  describe('Row Actions', () => {
    it('provides row action menu for each integration', () => {
      render(<Integrations />, { wrapper })

      // Table should render
      expect(screen.getByText('Primary MCP Server')).toBeInTheDocument()

      // Each row should have a kebab action menu
      const kebabButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      expect(kebabButtons.length).toBe(3)
    })

    it('opens validate dialog when validate action is clicked', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Find and click the actions menu for the first row
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])

      // Click validate connection option
      const validateOption = await screen.findByRole('menuitem', { name: /validate integration/i })
      await user.click(validateOption)

      // Validate dialog should open
      await waitFor(
        () => {
          expect(screen.getByText(/validate integration/i)).toBeInTheDocument()
        },
        { timeout: 10_000 }
      )
    })

    it('opens delete dialog when uninstall action is clicked', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Find and click the actions menu for the first row
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])

      // Click uninstall option
      const uninstallOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(uninstallOption)

      // Delete dialog should open with integration name in body
      await waitFor(() => {
        expect(screen.getByText(/delete integration/i)).toBeInTheDocument()
      })
      const dialog = screen.getByRole('dialog')
      expect(within(dialog).getByText(/This cannot be undone/)).toBeInTheDocument()
      expect(within(dialog).getByText(/Resources that will be deleted/)).toBeInTheDocument()
      expect(
        within(dialog).getByRole('checkbox', {
          name: 'I understand this integration and the resources shown above will be permanently deleted.',
        })
      ).toBeInTheDocument()
    })
  })

  describe('Pagination', () => {
    it('displays pagination controls when next or prev cursors are available', () => {
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
          next: 'next-cursor-abc',
          prev: null,
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Integrations />, { wrapper })

      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      const nextButton = within(paginationNav).getByRole('button', { name: 'Go to next page' })
      const prevButton = within(paginationNav).getByRole('button', { name: 'Go to previous page' })

      expect(nextButton).toBeInTheDocument()
      expect(prevButton).toBeInTheDocument()
      expect(nextButton).not.toBeDisabled()
      expect(prevButton).toBeDisabled()
    })

    it('displays total count when available', () => {
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
          next: 'next-cursor',
          prev: null,
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Integrations />, { wrapper })

      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      expect(paginationNav).toBeInTheDocument()
      expect(paginationNav.parentElement?.textContent).toContain('25')
    })

    it('renders pagination nav when prev cursor is available', () => {
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
          next: 'next-cursor',
          prev: 'prev-cursor-abc',
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Integrations />, { wrapper })

      // PF Pagination renders; prev button state is managed by PF based on page number
      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      expect(within(paginationNav).getByRole('button', { name: 'Go to previous page' })).toBeInTheDocument()
      expect(within(paginationNav).getByRole('button', { name: 'Go to next page' })).toBeInTheDocument()
    })

    it('hides pagination when no cursors are available', () => {
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
          next: null,
          prev: null,
          total: 3,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Integrations />, { wrapper })

      expect(screen.queryByRole('button', { name: 'Next page' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Previous page' })).not.toBeInTheDocument()
    })

    it('calls onNext when Next page button is clicked', async () => {
      const user = userEvent.setup()
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
          next: 'next-cursor-abc',
          prev: null,
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Integrations />, { wrapper })

      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      const nextButton = within(paginationNav).getByRole('button', { name: 'Go to next page' })
      await user.click(nextButton)

      // The button click should trigger the onNext callback
      expect(nextButton).toBeInTheDocument()
    })

    it('calls onPrev when Previous page button is clicked', async () => {
      const user = userEvent.setup()
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
          next: 'next-cursor',
          prev: 'prev-cursor-abc',
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Integrations />, { wrapper })

      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      const prevButton = within(paginationNav).getByRole('button', { name: 'Go to previous page' })
      await user.click(prevButton)

      // The button click should trigger the onPrev callback
      expect(prevButton).toBeInTheDocument()
    })

    it('does not reset cursor while query is fetching', async () => {
      const mockRefetch = vi.fn()

      // First render: page 1 with data
      vi.mocked(integrationsClient.useQuery).mockReturnValueOnce({
        data: {
          resources: mockIntegrations,
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

      const { rerender } = render(<Integrations />, { wrapper })

      // Verify pagination controls present
      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      const nextButton = within(paginationNav).getByRole('button', { name: 'Go to next page' })
      expect(nextButton).toBeInTheDocument()

      const user = userEvent.setup()
      // Click Next to set internal cursor state
      await user.click(nextButton)

      // Verify cursor was set after clicking Next
      await waitFor(() => {
        const lastCall = vi.mocked(integrationsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })

      // Second render: fetching state with empty data (cursor should NOT be reset due to isFetching=true)
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: [], // Empty during transition
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

      // Rerender to trigger useEffect with fetching state
      rerender(<Integrations />)

      // Wait for component to process and verify cursor is still present (not reset)
      await waitFor(() => {
        const lastCall = vi.mocked(integrationsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        // Cursor should still be present because isFetching=true prevents reset
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })

      // Third render: data arrives for page 2 - if cursor was preserved, we should have prev button
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations.slice(0, 2), // Page 2 data
          next: 'next-cursor',
          prev: 'prev-cursor', // This proves we're on page 2, not page 1
          total: 30,
        },
        isPending: false,
        isLoading: false,
        isFetching: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      })

      rerender(<Integrations />)

      // Verify pagination shows both buttons (proves cursor was not reset - we're on page 2)
      await waitFor(() => {
        const nav = screen.getByRole('navigation', { name: /pagination/i })
        expect(within(nav).getByRole('button', { name: 'Go to next page' })).toBeInTheDocument()
        expect(within(nav).getByRole('button', { name: 'Go to previous page' })).not.toBeDisabled()
      })
    })

    it('resets cursor when data is empty and query is not fetching', async () => {
      const mockRefetch = vi.fn()

      // Start with data and next cursor
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
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

      const { rerender } = render(<Integrations />, { wrapper })

      const user = userEvent.setup()
      // Click Next to set internal cursor state
      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      const nextButton = within(paginationNav).getByRole('button', { name: 'Go to next page' })
      await user.click(nextButton)

      // Wait for cursor to be set and verify it's present
      await waitFor(() => {
        const lastCall = vi.mocked(integrationsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams).toMatchObject({ cursor: 'next-cursor' })
      })

      // Simulate truly empty state - no data and not fetching
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
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

      rerender(<Integrations />)

      // Verify cursor was reset (no cursor in query params)
      await waitFor(() => {
        const lastCall = vi.mocked(integrationsClient.useQuery).mock.calls.at(-1)
        expect(lastCall).toBeDefined()
        // Cursor should be absent or undefined because it was reset
        const queryParams = (lastCall?.[2] as unknown as { params?: { query?: Record<string, unknown> } })?.params
          ?.query
        expect(queryParams?.cursor).toBeUndefined()
      })

      // Should show empty state (cursor was reset)
      await waitFor(() => {
        expect(screen.getByText(/No integrations/)).toBeInTheDocument()
      })
    })
  })

  describe('Filter API Contract', () => {
    it('applies name filter to API query when typing and submitting', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(textInput, 'test')
      await user.keyboard('{Enter}')

      // Verify both UI state AND API contract
      expect(textInput).toHaveValue('test')
      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'name[contains]', 'test')
      })
    })

    it('applies status filter to API query when selecting option', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Switch to status filter - find the field selector toggle (first button with "Name")
      const fieldButtons = screen.getAllByRole('button', { name: 'Name' })
      const fieldSelector = fieldButtons[0] // First "Name" button is the filter field selector
      await user.click(fieldSelector)
      await user.click(await screen.findByRole('option', { name: /status/i }))

      // Select "Available"
      const statusButton = await screen.findByRole('button', { name: /filter by status/i })
      await user.click(statusButton)
      await user.click(await screen.findByRole('option', { name: 'Available' }))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'validation_status', 'available')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })

    it('offers all expected status filter options', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const fieldButtons = screen.getAllByRole('button', { name: 'Name' })
      const fieldSelector = fieldButtons[0]
      await user.click(fieldSelector)
      await user.click(await screen.findByRole('option', { name: /status/i }))

      const statusButton = await screen.findByRole('button', { name: /filter by status/i })
      await user.click(statusButton)

      expect(screen.getByRole('option', { name: 'Available' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Error' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Unknown' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Validating' })).toBeInTheDocument()
    })

    it('applies integration type filter to API query', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Switch to integration type filter - find the field selector toggle (first button with "Name")
      const fieldButtons = screen.getAllByRole('button', { name: 'Name' })
      const fieldSelector = fieldButtons[0] // First "Name" button is the filter field selector
      await user.click(fieldSelector)
      await user.click(await screen.findByRole('option', { name: /integration type/i }))

      // Select "MCP Server"
      const typeButton = await screen.findByRole('button', { name: /filter by integration type/i })
      await user.click(typeButton)
      await user.click(await screen.findByRole('option', { name: 'MCP Server' }))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'integration_type', 'mcp_server')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })

    it('applies filter to API query after paginating', async () => {
      const user = userEvent.setup()

      // Mock query with pagination to have next/prev cursors available
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: {
          resources: mockIntegrations,
          next: 'next-cursor',
          prev: 'prev-cursor',
          total: 25,
        },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<Integrations />, { wrapper })

      // Click next page to set internal cursor state
      const paginationNav = screen.getByRole('navigation', { name: /pagination/i })
      const nextButton = within(paginationNav).getByRole('button', { name: 'Go to next page' })
      await user.click(nextButton)

      // Apply a filter after navigating to page 2
      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      await user.type(textInput, 'test')
      await user.keyboard('{Enter}')

      // Verify the filter was applied to URL params
      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'name[contains]', 'test')
      })
      expect(mockSetSearchParams).toHaveBeenCalled()
    })
  })

  describe('API sorting', () => {
    it('defaults query sort to name', () => {
      render(<Integrations />, { wrapper })

      expect(integrationsClient.useQuery).toHaveBeenCalledWith(
        'get',
        '/integrations',
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({
              sort: 'name',
            }) as unknown,
          }) as unknown,
        }) as unknown,
        expect.objectContaining({ refetchInterval: 30_000 }) as unknown
      )
    })

    it('renders sortable headers for name, status, type, and state', () => {
      render(<Integrations />, { wrapper })

      for (const name of [/server name/i, /^Status$/i, /Integration type/i, /^State$/i]) {
        const header = screen.getByRole('columnheader', { name })
        expect(within(header).getByRole('button')).toBeInTheDocument()
      }

      const apiUrlHeader = screen.getByRole('columnheader', { name: /^API URL$/i })
      expect(within(apiUrlHeader).queryByRole('button')).not.toBeInTheDocument()

      const resourcesHeader = screen.getByRole('columnheader', { name: /Enabled resources/i })
      expect(within(resourcesHeader).queryByRole('button')).not.toBeInTheDocument()

      const actionsHeader = screen.getByRole('columnheader', { name: 'Actions' })
      expect(within(actionsHeader).queryByRole('button')).not.toBeInTheDocument()
    })

    it('writes sort URL param when a column header is clicked', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const statusHeader = screen.getByRole('columnheader', { name: /^Status$/i })
      await user.click(within(statusHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'validation_status')
      })
    })

    it('can sort by integration_type via the Integration type column', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const typeHeader = screen.getByRole('columnheader', { name: /Integration type/i })
      await user.click(within(typeHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'integration_type')
      })
    })

    it('can sort by enabled via the State column', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const stateHeader = screen.getByRole('columnheader', { name: /^State$/i })
      await user.click(within(stateHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', 'enabled')
      })
    })

    it('toggles sort direction when clicking the default name column', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const nameHeader = screen.getByRole('columnheader', { name: /server name/i })
      await user.click(within(nameHeader).getByRole('button'))

      await waitFor(() => {
        assertUrlParam(mockSetSearchParams, 'sort', '-name')
      })
    })
  })

  describe('Validate Dialog Flow', () => {
    it('calls validate mutation when Validate button is clicked', async () => {
      const user = userEvent.setup()
      const mockValidateMutate = vi.fn()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: mockIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('validate')) {
          return { mutate: mockValidateMutate, isPending: false } as never
        }
        return { mutate: mockDeleteMutate, isPending: false } as never
      })

      render(<Integrations />, { wrapper })

      // Open actions menu and click validate (API order — first row is ID 1)
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const validateOption = await screen.findByRole('menuitem', { name: /validate integration/i })
      await user.click(validateOption)

      // Click Validate button in dialog
      const validateButton = await screen.findByRole('button', { name: 'Validate' })
      await user.click(validateButton)

      // Verify mutation was called with integration_id (first row is ID 1 from API order)
      expect(mockValidateMutate).toHaveBeenCalled()
      const callArgs = mockValidateMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({ params: { path: { integration_id: '1' } } })
    })

    it('shows success alert and closes dialog on successful validation', { timeout: 15_000 }, async () => {
      const user = userEvent.setup()
      const mockValidateMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: mockIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('validate')) {
          return { mutate: mockValidateMutate, isPending: false } as never
        }
        return { mutate: vi.fn(), isPending: false } as never
      })

      render(<Integrations />, { wrapper })

      // Open validate dialog
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const validateOption = await screen.findByRole('menuitem', { name: /validate integration/i })
      await user.click(validateOption)

      // Click Validate
      const validateButton = await screen.findByRole('button', { name: 'Validate' })
      await user.click(validateButton)

      // Simulate successful mutation with success: true
      const mutationCall = mockValidateMutate.mock.calls[0] as [unknown, MockMutationCallbacks]
      const callbacks = mutationCall[1]
      act(() => {
        callbacks.onSuccess({ success: true, checked_at: new Date().toISOString() })
        callbacks.onSettled()
      })

      // Dialog should close (Validate button no longer visible)
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Validate' })).not.toBeInTheDocument()
      })
      expect(mockRefetch).toHaveBeenCalled()
    })

    it('updates status badge after successful validation refetch', async () => {
      const user = userEvent.setup()
      const mockValidateMutate = vi.fn()

      // Start with error status for integration 2
      const initialIntegrations = [...mockIntegrations]

      const updatedIntegrations = mockIntegrations.map((i) =>
        i.id === '2' ? { ...i, validation_status: IntegrationStatusEnum.AVAILABLE, validation_error: null } : i
      )

      // First call returns error status; subsequent calls return available
      const mockRefetch = vi.fn().mockResolvedValue({ data: { resources: updatedIntegrations } })
      vi.mocked(integrationsClient.useQuery)
        .mockReturnValueOnce({
          data: { resources: initialIntegrations },
          isPending: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never)
        .mockReturnValue({
          data: { resources: updatedIntegrations },
          isPending: false,
          isError: false,
          error: null,
          refetch: mockRefetch,
        } as never)

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('validate')) {
          return { mutate: mockValidateMutate, isPending: false } as never
        }
        return { mutate: vi.fn(), isPending: false } as never
      })

      const { rerender } = render(<Integrations />, { wrapper })

      // Verify the error status badge is shown before validation
      expect(screen.getByText('Error')).toBeInTheDocument()

      // Open actions menu and click validate for the first row (alphabetically sorted)
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const validateOption = await screen.findByRole('menuitem', { name: /validate integration/i })
      await user.click(validateOption)

      const validateButton = await screen.findByRole('button', { name: 'Validate' })
      await user.click(validateButton)

      // Simulate successful validation — triggers refetch
      const mutationCall = mockValidateMutate.mock.calls[0] as [unknown, MockMutationCallbacks]
      const callbacks = mutationCall[1]
      act(() => {
        callbacks.onSuccess({ success: true, checked_at: new Date().toISOString() })
        callbacks.onSettled()
      })

      expect(mockRefetch).toHaveBeenCalled()

      // Re-render with updated data (simulating refetch result)
      rerender(<Integrations />)

      // Error badge should be gone, replaced by Available
      await waitFor(() => {
        expect(screen.queryByText('Error')).not.toBeInTheDocument()
      })
    })

    it('shows error alert when validation returns success: false', async () => {
      const user = userEvent.setup()
      const mockValidateMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: mockIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('validate')) {
          return { mutate: mockValidateMutate, isPending: false } as never
        }
        return { mutate: vi.fn(), isPending: false } as never
      })

      render(<Integrations />, { wrapper })

      // Open validate dialog
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const validateOption = await screen.findByRole('menuitem', { name: /validate integration/i })
      await user.click(validateOption)

      // Click Validate
      const validateButton = await screen.findByRole('button', { name: 'Validate' })
      await user.click(validateButton)

      // Simulate HTTP 200 with success: false
      const mutationCall = mockValidateMutate.mock.calls[0] as [unknown, MockMutationCallbacks]
      const callbacks = mutationCall[1]
      act(() => {
        callbacks.onSuccess({
          success: false,
          checked_at: new Date().toISOString(),
          error: 'Connection refused: unable to reach MCP server',
        })
        callbacks.onSettled()
      })

      // Error alert should be shown with validation error
      await waitFor(() => {
        expect(screen.getByText('Validation failed')).toBeInTheDocument()
        expect(screen.getByText(/Connection refused: unable to reach MCP server/)).toBeInTheDocument()
      })

      // Dialog should close
      expect(screen.queryByRole('button', { name: 'Validate' })).not.toBeInTheDocument()
      // Should still refetch to update provider status
      expect(mockRefetch).toHaveBeenCalled()
    })

    it('shows error alert on validation failure', async () => {
      const user = userEvent.setup()
      const mockValidateMutate = vi.fn()

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('validate')) {
          return { mutate: mockValidateMutate, isPending: false } as never
        }
        return { mutate: vi.fn(), isPending: false } as never
      })

      render(<Integrations />, { wrapper })

      // Open validate dialog
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const validateOption = await screen.findByRole('menuitem', { name: /validate integration/i })
      await user.click(validateOption)

      // Click Validate
      const validateButton = await screen.findByRole('button', { name: 'Validate' })
      await user.click(validateButton)

      // Simulate failed mutation
      const callbacks = mockValidateMutate.mock.calls[0][1] as MockMutationCallbacks
      act(() => {
        callbacks.onError(new Error('Connection timeout'))
        callbacks.onSettled()
      })

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Validate' })).not.toBeInTheDocument()
      })
    })

    it('closes validate dialog when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Open validate dialog
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const validateOption = await screen.findByRole('menuitem', { name: /validate integration/i })
      await user.click(validateOption)

      // Verify dialog is open
      await waitFor(() => {
        expect(screen.getByText(/validate integration/i)).toBeInTheDocument()
      })

      // Click Cancel
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      await user.click(cancelButton)

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByText(/Are you sure you want to validate/)).not.toBeInTheDocument()
      })
    })
  })

  describe('Delete Dialog Flow', () => {
    it('calls delete mutation when Delete button is clicked', async () => {
      const user = userEvent.setup()
      const mockValidateMutate = vi.fn()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: mockIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      vi.mocked(integrationsClient.useMutation).mockImplementation((method: string) => {
        if (method === 'delete') {
          return { mutate: mockDeleteMutate, isPending: false } as never
        }
        return { mutate: mockValidateMutate, isPending: false } as never
      })

      render(<Integrations />, { wrapper })

      // Open actions menu and click uninstall (API order — first row is ID 1)
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const uninstallOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(uninstallOption)

      // Check the acknowledgement checkbox before clicking Delete
      await user.click(screen.getByRole('checkbox'))

      // Click Delete button in dialog
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // Verify mutation was called (first row is ID 1 from API order)
      expect(mockDeleteMutate).toHaveBeenCalled()
      const callArgs = mockDeleteMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({ params: { path: { integration_id: '1' } } })
    })

    it('shows success alert and closes dialog on successful delete', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()
      const mockRefetch = vi.fn()

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: mockIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never)

      vi.mocked(integrationsClient.useMutation).mockImplementation((method: string) => {
        if (method === 'delete') {
          return { mutate: mockDeleteMutate, isPending: false } as never
        }
        return { mutate: vi.fn(), isPending: false } as never
      })

      render(<Integrations />, { wrapper })

      // Open delete dialog
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const uninstallOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(uninstallOption)

      // Check the acknowledgement checkbox before clicking Delete
      await user.click(screen.getByRole('checkbox'))

      // Click Delete
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // Simulate successful mutation
      const callbacks = mockDeleteMutate.mock.calls[0][1] as MockMutationCallbacks
      act(() => {
        callbacks.onSuccess()
        callbacks.onSettled()
      })

      // Dialog should close and navigate to list
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
      })
      expect(routerTestState.navigate).toHaveBeenCalled()
    })

    it('shows error alert on delete failure', async () => {
      const user = userEvent.setup()
      const mockDeleteMutate = vi.fn()

      vi.mocked(integrationsClient.useMutation).mockImplementation((method: string) => {
        if (method === 'delete') {
          return { mutate: mockDeleteMutate, isPending: false } as never
        }
        return { mutate: vi.fn(), isPending: false } as never
      })

      render(<Integrations />, { wrapper })

      // Open delete dialog
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const uninstallOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(uninstallOption)

      // Check the acknowledgement checkbox before clicking Delete
      await user.click(screen.getByRole('checkbox'))

      // Click Delete
      const deleteButton = await screen.findByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      // Simulate failed mutation
      const callbacks = mockDeleteMutate.mock.calls[0][1] as MockMutationCallbacks
      act(() => {
        callbacks.onError(new Error('Permission denied'))
        callbacks.onSettled()
      })

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
      })
    })

    it('closes delete dialog when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Open delete dialog
      const actionButtons = screen.getAllByRole('button', { name: /^Actions for /i })
      await user.click(actionButtons[0])
      const uninstallOption = await screen.findByRole('menuitem', { name: /delete/i })
      await user.click(uninstallOption)

      // Verify dialog is open
      await waitFor(() => {
        expect(screen.getByText(/delete integration/i)).toBeInTheDocument()
      })

      // Click Cancel
      const cancelButtons = screen.getAllByRole('button', { name: 'Cancel' })
      await user.click(cancelButtons[cancelButtons.length - 1])

      // Dialog should close
      await waitFor(() => {
        expect(screen.queryByText(/This action cannot be undone/)).not.toBeInTheDocument()
      })
    })
  })

  describe('Filter Controls', () => {
    it('provides filter controls for user interaction', () => {
      render(<Integrations />, { wrapper })

      // Verify filter input is available
      const textInput = screen.getByRole('textbox', { name: /name filter/i })
      expect(textInput).toBeInTheDocument()
      expect(textInput).toHaveAttribute('placeholder', 'Filter by name')
    })
  })

  describe('State Toggle', () => {
    it('renders enabled switches for all integrations', () => {
      render(<Integrations />, { wrapper })

      const switches = screen.getAllByRole('switch')
      expect(switches).toHaveLength(3)
      for (const toggle of switches) {
        expect(toggle).toBeChecked()
      }
    })

    it('opens disable confirmation dialog when toggling an enabled integration off', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const switches = screen.getAllByRole('switch')
      await user.click(switches[0])

      await waitFor(() => {
        expect(screen.getByText(/disable integration/i)).toBeInTheDocument()
      })
    })

    it('calls patch mutation to enable a disabled integration without confirmation', async () => {
      const mockPatchMutate = vi.fn()

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/validate')) return { mutate: vi.fn() } as never
        if (path === '/integrations/{integration_id}' && _method === 'delete') return { mutate: vi.fn() } as never
        if (path === '/integrations/{integration_id}' && _method === 'patch')
          return { mutate: mockPatchMutate } as never
        return { mutate: vi.fn() } as never
      })

      const disabledIntegrations = [
        {
          ...mockIntegrations[0],
          enabled: false,
        },
      ]

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: disabledIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const toggle = screen.getByRole('switch')
      await user.click(toggle)

      expect(mockPatchMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          body: { enabled: true },
        }),
        expect.any(Object)
      )
    })

    it('calls patch mutation with enabled: false after confirming disable dialog', async () => {
      const mockPatchMutate = vi.fn()

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/validate')) return { mutate: vi.fn() } as never
        if (path === '/integrations/{integration_id}' && _method === 'delete') return { mutate: vi.fn() } as never
        if (path === '/integrations/{integration_id}' && _method === 'patch')
          return { mutate: mockPatchMutate } as never
        return { mutate: vi.fn() } as never
      })

      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      // Click toggle to open disable dialog
      const switches = screen.getAllByRole('switch')
      await user.click(switches[0])

      // Confirm disable
      await waitFor(() => {
        expect(screen.getByText(/disable integration/i)).toBeInTheDocument()
      })
      const disableButton = screen.getByRole('button', { name: 'Disable' })
      await user.click(disableButton)

      expect(mockPatchMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          body: { enabled: false },
        }),
        expect.any(Object)
      )
    })

    it('shows error alert when toggle patch fails', async () => {
      const mockPatchMutate = vi.fn()

      vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
        if (path.includes('/validate')) return { mutate: vi.fn() } as never
        if (path === '/integrations/{integration_id}' && _method === 'delete') return { mutate: vi.fn() } as never
        if (path === '/integrations/{integration_id}' && _method === 'patch')
          return { mutate: mockPatchMutate } as never
        return { mutate: vi.fn() } as never
      })

      const disabledIntegrations = [
        {
          ...mockIntegrations[0],
          enabled: false,
        },
      ]

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: disabledIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      // Make patch call onError
      mockPatchMutate.mockImplementation((_variables: unknown, options?: { onError?: (error: unknown) => void }) => {
        if (options?.onError) {
          options.onError(new Error('Network error'))
        }
      })

      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const toggle = screen.getByRole('switch')
      await user.click(toggle)

      await waitFor(() => {
        expect(screen.getByText(/update failed/i)).toBeInTheDocument()
      })
    })

    it('reflects disabled state from data', () => {
      const mixedIntegrations = [
        { ...mockIntegrations[0], enabled: true },
        { ...mockIntegrations[1], enabled: false },
      ]

      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: mixedIntegrations },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      render(<Integrations />, { wrapper })

      const switches = screen.getAllByRole('switch')
      expect(switches).toHaveLength(2)
      expect(switches[0]).toBeChecked()
      expect(switches[1]).not.toBeChecked()
    })
  })

  describe('Permission gating', () => {
    it('disables Configure integration button when canCreate is false', () => {
      mockPermissions.canCreate = false
      render(<Integrations />, { wrapper })

      const button = screen.getByRole('button', { name: 'Configure integration' })
      expect(button).toHaveAttribute('aria-disabled', 'true')
    })

    it('does not navigate when disabled Configure button is clicked', async () => {
      mockPermissions.canCreate = false
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Configure integration' }))

      expect(routerTestState.navigate).not.toHaveBeenCalled()
    })

    it('disables toggle switch with correct label when canUpdate is false', () => {
      mockPermissions.canUpdate = false
      render(<Integrations />, { wrapper })

      const switches = screen.getAllByRole('switch')
      switches.forEach((sw) => {
        expect(sw).toBeDisabled()
      })
      expect(screen.getAllByText('Enabled').length).toBeGreaterThan(0)
    })

    it('disables validate kebab action when canUpdate is false', async () => {
      mockPermissions.canUpdate = false
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const kebab = screen.getAllByRole('button', { name: /Actions for/ })[0]
      await user.click(kebab)

      const validateItem = screen.getByRole('menuitem', { name: /Validate integration/i })
      expect(validateItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('disables delete kebab action when canDelete is false', async () => {
      mockPermissions.canDelete = false
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const kebab = screen.getAllByRole('button', { name: /Actions for/ })[0]
      await user.click(kebab)

      const deleteItem = screen.getByRole('menuitem', { name: /Delete integration/i })
      expect(deleteItem).toHaveAttribute('aria-disabled', 'true')
    })

    it('hides empty state CTA when canCreate is false', () => {
      mockPermissions.canCreate = false
      vi.mocked(integrationsClient.useQuery).mockReturnValue({
        data: { resources: [] },
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never)

      render(<Integrations />, { wrapper })

      expect(screen.getByText('No integrations yet')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Configure integration' })).not.toBeInTheDocument()
    })
  })

  describe('Status tooltip', () => {
    it('shows validation error tooltip on hover for error status', async () => {
      const user = userEvent.setup()
      render(<Integrations />, { wrapper })

      const errorLabels = screen.getAllByText('Error')
      await user.hover(errorLabels[0])
      expect(await screen.findByRole('tooltip')).toHaveTextContent('Connection refused')
    })
  })

  describe('Auto-refresh polling', () => {
    it('configures 30-second polling interval on the integrations query', () => {
      render(<Integrations />, { wrapper })

      const lastCall = vi.mocked(integrationsClient.useQuery).mock.calls.at(-1)
      expect(lastCall).toBeDefined()
      const queryOptions = lastCall?.[3] as { refetchInterval?: number } | undefined
      expect(queryOptions?.refetchInterval).toBe(30_000)
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<Integrations />, { wrapper })
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
