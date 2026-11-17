import type { IntegrationsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { integrationsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts/AlertProvider'

import { IntegrationModelsTab } from './IntegrationModelsTab'

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

const mockModels = [
  {
    id: 'm1',
    integration_id: 'int-1',
    model_id: 'gpt-4o',
    name: 'GPT-4o',
    description: 'Large language model',
    enabled: true,
    is_default: true,
  },
  {
    id: 'm2',
    integration_id: 'int-1',
    model_id: 'gpt-3.5-turbo',
    name: 'GPT-3.5 Turbo',
    description: 'Fast model',
    enabled: true,
    is_default: false,
  },
  {
    id: 'm3',
    integration_id: 'int-1',
    model_id: 'gpt-4o-mini',
    name: 'GPT-4o Mini',
    description: 'Small model',
    enabled: false,
    is_default: false,
  },
]

describe('IntegrationModelsTab', () => {
  const mockRefreshMutate = vi.fn()
  const mockOnRefreshed = vi.fn().mockResolvedValue(undefined)
  const mockRefetchModels = vi.fn().mockResolvedValue(undefined)
  const mockHandleSelectAll = vi.fn()
  const mockHandleSelectWithDefaultClear = vi.fn()
  const mockHandleSetDefault = vi.fn()
  const mockHandleRemoveDefault = vi.fn()
  const mockResetSelectionToServer = vi.fn()
  const mockResetDefault = vi.fn()

  function setupMutationMocks() {
    vi.mocked(integrationsClient.useMutation).mockImplementation((_method: string, path: string) => {
      if (path.includes('/refresh')) {
        return { mutateAsync: mockRefreshMutate.mockResolvedValue({}), isPending: false } as never
      }
      return { mutateAsync: vi.fn(), isPending: false } as never
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    setupMutationMocks()
  })

  function renderTab(
    overrides: {
      canUpdate?: boolean
      models?: typeof mockModels
      isLoading?: boolean
      error?: string | null
      enabledModelIds?: Set<string>
      enabledCount?: number
      allSelected?: boolean
      defaultModelId?: string | null
      refreshStatus?: IntegrationsAPI.components['schemas']['IntegrationRefreshStatus'] | null
      refreshError?: string | null
    } = {}
  ) {
    const {
      canUpdate = true,
      models = mockModels,
      isLoading = false,
      error = null,
      enabledModelIds = new Set(['m1', 'm2']),
      enabledCount = 2,
      allSelected = false,
      defaultModelId = 'm1',
      refreshStatus = null,
      refreshError = null,
    } = overrides
    return render(
      <IntegrationModelsTab
        integrationId="int-1"
        models={models}
        isLoading={isLoading}
        error={error}
        refetchModels={mockRefetchModels}
        enabledModelIds={enabledModelIds}
        enabledCount={enabledCount}
        allSelected={allSelected}
        handleSelectAll={mockHandleSelectAll}
        defaultModelId={defaultModelId}
        handleSelectWithDefaultClear={mockHandleSelectWithDefaultClear}
        handleSetDefault={mockHandleSetDefault}
        handleRemoveDefault={mockHandleRemoveDefault}
        resetSelectionToServer={mockResetSelectionToServer}
        resetDefault={mockResetDefault}
        lastRefreshedAt="2026-01-01T10:00:00Z"
        refreshStatus={refreshStatus}
        refreshError={refreshError}
        canUpdate={canUpdate}
        onRefreshed={mockOnRefreshed}
      />,
      { wrapper }
    )
  }

  describe('Rendering', () => {
    it('renders models in a table with checkboxes', () => {
      renderTab()
      expect(screen.getByText('GPT-4o')).toBeInTheDocument()
      expect(screen.getByText('GPT-3.5 Turbo')).toBeInTheDocument()
      expect(screen.getByText('GPT-4o Mini')).toBeInTheDocument()
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
      expect(screen.getByRole('textbox', { name: /name filter/i })).toBeInTheDocument()
    })

    it('shows Default badge on the default model', () => {
      renderTab()
      expect(screen.getByText('Default')).toBeInTheDocument()
    })

    it('renders model descriptions', () => {
      renderTab()
      expect(screen.getByText('Large language model')).toBeInTheDocument()
      expect(screen.getByText('Fast model')).toBeInTheDocument()
    })
  })

  describe('Model selection', () => {
    it('calls handleSelectWithDefaultClear when toggling a model checkbox', async () => {
      const user = userEvent.setup()
      renderTab()
      const rows = screen.getAllByRole('row')
      const row = rows.find((r) => r.textContent?.includes('GPT-3.5 Turbo'))
      await user.click(within(row!).getByRole('checkbox'))
      expect(mockHandleSelectWithDefaultClear).toHaveBeenCalledWith('m2', false)
    })

    it('calls handleSelectAll when select-all checkbox is clicked', async () => {
      const user = userEvent.setup()
      renderTab()
      const thead = screen.getAllByRole('rowgroup')[0]
      await user.click(within(thead).getByRole('checkbox'))
      expect(mockHandleSelectAll).toHaveBeenCalled()
    })
  })

  describe('Search filter', () => {
    it('filters models by name', async () => {
      const user = userEvent.setup()
      renderTab()
      await user.type(screen.getByRole('textbox', { name: /name filter/i }), 'GPT-4o{Enter}')
      expect(screen.getAllByText('GPT-4o').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('GPT-4o Mini')).toBeInTheDocument()
      expect(screen.queryByText('GPT-3.5 Turbo')).not.toBeInTheDocument()
    })
  })

  describe('Default model via kebab', () => {
    it('shows Set as default for enabled non-default models', async () => {
      const user = userEvent.setup()
      renderTab()
      await user.click(screen.getAllByRole('button', { name: /Actions for GPT-3.5 Turbo/ })[0])
      expect(screen.getByRole('menuitem', { name: /Set as default/ })).toBeInTheDocument()
    })

    it('shows Remove default for the current default model', async () => {
      const user = userEvent.setup()
      renderTab()
      await user.click(screen.getAllByRole('button', { name: /Actions for GPT-4o$/ })[0])
      expect(screen.getByRole('menuitem', { name: 'Remove default model' })).toBeInTheDocument()
    })

    it('no kebab actions for disabled models', () => {
      renderTab()
      expect(screen.queryByRole('button', { name: /Actions for GPT-4o Mini/ })).not.toBeInTheDocument()
    })

    it('calls handleSetDefault when Set as default is clicked', async () => {
      const user = userEvent.setup()
      renderTab()
      await user.click(screen.getAllByRole('button', { name: /Actions for GPT-3.5 Turbo/ })[0])
      await user.click(screen.getByRole('menuitem', { name: /Set as default/ }))
      expect(mockHandleSetDefault).toHaveBeenCalledWith('m2')
    })

    it('calls handleRemoveDefault when Remove default is clicked', async () => {
      const user = userEvent.setup()
      renderTab()
      await user.click(screen.getAllByRole('button', { name: /Actions for GPT-4o$/ })[0])
      await user.click(screen.getByRole('menuitem', { name: 'Remove default model' }))
      expect(mockHandleRemoveDefault).toHaveBeenCalledWith('m1')
    })
  })

  describe('Refresh', () => {
    it('calls refresh mutation when refresh button clicked', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({ refresh_status: 'available', refresh_error: null })
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      expect(mockRefreshMutate).toHaveBeenCalled()
    })

    it('resets selection and default before refreshing', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({ refresh_status: 'available', refresh_error: null })
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      expect(mockResetSelectionToServer).toHaveBeenCalled()
      expect(mockResetDefault).toHaveBeenCalled()
    })

    it('shows success alert when refresh succeeds', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({ refresh_status: 'available', refresh_error: null })
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      await waitFor(() => {
        expect(screen.getByText('Models refreshed')).toBeInTheDocument()
      })
    })

    it('shows error alert when refresh returns error status', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({ refresh_status: 'error', refresh_error: 'Connection refused' })
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      await waitFor(() => {
        expect(screen.getByText('Refresh failed')).toBeInTheDocument()
      })
    })

    it('shows warning alert (with the warning message) when refresh returns warning status', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({
        refresh_status: 'warning',
        refresh_error: 'Default model "gpt-4o" is no longer offered',
      })
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      await waitFor(() => {
        expect(screen.getByText('Refreshed with warnings')).toBeInTheDocument()
        expect(screen.getByText('Default model "gpt-4o" is no longer offered')).toBeInTheDocument()
      })
    })

    it('shows a fallback warning message when refresh returns warning with no error text', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({ refresh_status: 'warning', refresh_error: null })
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      await waitFor(() => {
        expect(screen.getByText('Models refreshed, but a warning was reported.')).toBeInTheDocument()
      })
    })

    it('shows a fallback error message when refresh returns error with no error text', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue({ refresh_status: 'error', refresh_error: null })
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      await waitFor(() => {
        expect(screen.getByText('Failed to refresh models.')).toBeInTheDocument()
      })
    })

    it('shows the success toast when refresh returns no status', async () => {
      const user = userEvent.setup()
      mockOnRefreshed.mockResolvedValue(undefined)
      renderTab()
      await user.click(screen.getByRole('button', { name: 'Refresh models' }))
      await waitFor(() => {
        expect(screen.getByText('Models refreshed')).toBeInTheDocument()
      })
    })

    it('refresh button is disabled when canUpdate is false', () => {
      renderTab({ canUpdate: false })
      expect(screen.getByRole('button', { name: 'Refresh models' })).toHaveAttribute('aria-disabled', 'true')
    })
  })

  describe('Warning status', () => {
    it('shows a persistent warning indicator when refresh_status is warning', () => {
      renderTab({ refreshStatus: 'warning', refreshError: 'Default model no longer offered' })
      expect(screen.getByText('Warning')).toBeInTheDocument()
    })

    it('does not show the warning indicator when refresh_status is available', () => {
      renderTab({ refreshStatus: 'available' })
      expect(screen.queryByText('Warning')).not.toBeInTheDocument()
    })

    it('renders the warning indicator with a fallback tooltip when refreshError is null', () => {
      renderTab({ refreshStatus: 'warning', refreshError: null })
      expect(screen.getByText('Warning')).toBeInTheDocument()
    })
  })

  describe('Loading and error states', () => {
    it('shows loading state while models are being fetched', () => {
      renderTab({ isLoading: true, models: [] })
      expect(screen.getByRole('progressbar', { name: /loading/i })).toBeInTheDocument()
    })

    it('shows error state when model fetch fails', () => {
      renderTab({ error: 'Failed to fetch models', models: [] })
      expect(screen.getByText('Unable to load models')).toBeInTheDocument()
    })
  })

  describe('Empty state', () => {
    it('shows empty state when no models exist', () => {
      renderTab({ models: [], enabledModelIds: new Set(), enabledCount: 0 })
      expect(screen.getByText('No models discovered yet')).toBeInTheDocument()
    })

    it('empty state has a refresh button', () => {
      renderTab({ models: [], enabledModelIds: new Set(), enabledCount: 0 })
      expect(screen.getByRole('button', { name: 'Refresh models' })).toBeInTheDocument()
    })

    it('empty state hides refresh button when canUpdate is false', () => {
      renderTab({ models: [], enabledModelIds: new Set(), enabledCount: 0, canUpdate: false })
      expect(screen.queryByRole('button', { name: 'Refresh models' })).not.toBeInTheDocument()
    })
  })

  describe('Permission gating', () => {
    it('disables row checkboxes when canUpdate is false', () => {
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
    it('has no accessibility violations with models rendered', async () => {
      const { container } = renderTab()
      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      const { container } = renderTab({ models: [], enabledModelIds: new Set(), enabledCount: 0 })
      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })

    it('has no accessibility violations in warning state', async () => {
      const { container } = renderTab({
        refreshStatus: 'warning',
        refreshError: 'Default model no longer offered',
      })
      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })
})
