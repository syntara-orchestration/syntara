import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { settingsClient } from '../../../client'
import { useFileStorageStatus } from '../../../hooks/useFileStorageStatus'
import { WORKFLOW_ENGINE_DEFAULTS_QUERY_KEY } from '../../builder/hooks/useWorkflowEngineDefaults'

import Settings from './Settings'
import { useAllSettings } from './useAllSettings'
import { useSettingsPermissions } from './useSettingsPermissions'

const { mockSetLocation, mockLocation, mockInvalidateQueries } = vi.hoisted(() => ({
  mockSetLocation: vi.fn(),
  mockLocation: { value: '/system-administration/settings/context_manager' },
  mockInvalidateQueries: vi.fn(() => Promise.resolve()),
}))

const mockMutate = vi.fn()
const mockShowSuccess = vi.fn()
const mockShowError = vi.fn()
const mockShowWarning = vi.fn()

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual('@tanstack/react-query')
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
  }
})
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { MockLink } = await import('../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useNavigate: () => mockSetLocation,
    useRouterState: vi.fn((opts?: { select?: (s: { location: { pathname: string } }) => unknown }) => {
      const state = { location: { pathname: mockLocation.value } }
      return opts?.select ? opts.select(state) : state
    }),
  }
})
vi.mock('../../../hooks/routing/useNavigate', () => ({
  useNavigate: () => mockSetLocation,
}))

vi.mock('../../../client', () => ({
  settingsClient: {
    useQuery: vi.fn(),
    useMutation: () => ({ mutate: mockMutate, isPending: false }),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showSuccess: mockShowSuccess, showError: mockShowError, showWarning: mockShowWarning }),
}))

vi.mock('../../../hooks/useApiErrorAlert', () => ({
  useApiErrorAlert: vi.fn(),
}))

vi.mock('../../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: () => () => vi.fn(),
}))

vi.mock('./useSettingsPermissions', () => ({
  useSettingsPermissions: vi.fn(() => ({ canRead: true, canWrite: true })),
}))

vi.mock('../../../hooks/useFileStorageStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../hooks/useFileStorageStatus')>()),
  useFileStorageStatus: vi
    .fn()
    .mockReturnValue({ isConfigured: true, isLoading: false, isError: false, status: 'ok' as const }),
}))

vi.mock('./useAllSettings', () => ({
  useAllSettings: vi.fn(),
}))

const mockCategories = {
  resources: [
    {
      slug: 'context_manager',
      name: 'Context Manager',
      description: null,
      group_names: ['Compression', 'Token limits'],
    },
    { slug: 'application', name: 'Application', description: null, group_names: ['General'] },
  ],
}

const mockSettings = {
  resources: [
    {
      id: '1',
      key: 'context_manager.max_total_tokens',
      name: 'Max total tokens',
      description: 'Maximum total tokens',
      helper_text: 'Minimum 1 token',
      depends_on: null,
      category: 'context_manager',
      group: 'Token limits',
      value: null,
      default_value: 4000,
      effective_value: 4000,
      value_type: 'integer' as const,
      requires_restart: false,
      cache_ttl_seconds: null,
      validation_schema: null,
      version: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: '2',
      key: 'application.debug_mode',
      name: 'Debug mode',
      description: 'Enable debug logging',
      helper_text: null,
      depends_on: null,
      category: 'application',
      group: 'General',
      value: null,
      default_value: false,
      effective_value: false,
      value_type: 'boolean' as const,
      requires_restart: false,
      cache_ttl_seconds: null,
      validation_schema: null,
      version: 1,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  next: null,
  prev: null,
}

function mockQueries({ isPending = false, error = null as Error | null } = {}) {
  vi.mocked(settingsClient.useQuery).mockImplementation((_method: string, path: string) => {
    if (path === '/settings/categories') {
      return {
        data: isPending ? undefined : mockCategories,
        isPending,
        error,
        refetch: vi.fn(),
      } as never
    }
    return {
      data: undefined,
      isPending: false,
      error: null,
      refetch: vi.fn(),
    } as never
  })
  vi.mocked(useAllSettings).mockReturnValue({
    settings: isPending ? [] : mockSettings.resources,
    isLoading: isPending,
    error,
    refetch: vi.fn(),
  })
}

describe('Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLocation.value = '/system-administration/settings/context_manager'
    vi.mocked(useFileStorageStatus).mockReturnValue({
      isConfigured: true,
      isLoading: false,
      isError: false,
      status: 'ok' as const,
    })
  })

  it('has no accessibility violations', async () => {
    mockQueries()
    let container: HTMLElement
    let results: Awaited<ReturnType<typeof axe>>
    // eslint-disable-next-line testing-library/no-unnecessary-act -- axe async scan triggers React effects outside act
    await act(async () => {
      ;({ container } = render(<Settings />))
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })

  it('renders loading state when queries are pending', () => {
    mockQueries({ isPending: true })
    render(<Settings />)

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('renders error state when query fails', () => {
    mockQueries({ error: new Error('Network error') })
    render(<Settings />)

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
  })

  it('renders category tabs from API data', () => {
    mockQueries()
    render(<Settings />)

    expect(screen.getByRole('tab', { name: 'Context Manager' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Application' })).toBeInTheDocument()
  })

  it('does not show a Configuration parent breadcrumb', () => {
    mockQueries()
    render(<Settings />)

    expect(screen.queryByRole('link', { name: 'Configuration' })).not.toBeInTheDocument()
  })

  it('navigates to the correct URL when a tab is clicked', async () => {
    const user = userEvent.setup()
    mockQueries()
    render(<Settings />)

    await user.click(screen.getByRole('tab', { name: 'Application' }))

    expect(mockSetLocation).toHaveBeenCalledWith({ to: '/system-administration/settings/application' })
  })

  it('renders correct content when URL points to a different tab', () => {
    mockLocation.value = '/system-administration/settings/application'
    mockQueries()
    render(<Settings />)

    expect(screen.getByText('Debug mode')).toBeInTheDocument()
    expect(screen.queryByText('Max total tokens')).not.toBeInTheDocument()
  })

  it('shows first category tab content by default', () => {
    mockQueries()
    render(<Settings />)

    expect(screen.getByText('Max total tokens')).toBeInTheDocument()
  })

  it('groups settings by category correctly', () => {
    mockQueries()
    render(<Settings />)

    // First tab (context_manager) should show its setting
    expect(screen.getByText('Max total tokens')).toBeInTheDocument()
    // Second tab (application) setting should not be visible
    expect(screen.queryByText('Debug mode')).not.toBeInTheDocument()
  })

  it('save button is disabled when no edits', () => {
    mockQueries()
    render(<Settings />)

    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('save button is enabled after editing a setting', async () => {
    const user = userEvent.setup()
    mockQueries()
    render(<Settings />)

    await user.click(screen.getByRole('button', { name: /plus/i }))
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  })

  it('save calls bulkUpdate with edits and clears on success', async () => {
    const user = userEvent.setup()
    mockMutate.mockImplementation((_payload: unknown, callbacks: { onSuccess: () => void }) => {
      callbacks.onSuccess()
    })
    mockQueries()
    render(<Settings />)

    await user.click(screen.getByRole('button', { name: /plus/i }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(mockMutate).toHaveBeenCalledWith(
      {
        body: {
          updates: [{ key: 'context_manager.max_total_tokens', value: 4001, expected_version: 1 }],
        },
      },
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    )
    expect(mockShowSuccess).not.toHaveBeenCalled()
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: WORKFLOW_ENGINE_DEFAULTS_QUERY_KEY })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('save shows version conflict error and clears edits', async () => {
    const user = userEvent.setup()
    mockMutate.mockImplementation((_payload: unknown, callbacks: { onError: (e: { code: string }) => void }) => {
      callbacks.onError({ code: 'SETTING_VERSION_CONFLICT' })
    })
    mockQueries()
    render(<Settings />)

    await user.click(screen.getByRole('button', { name: /plus/i }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Version conflict',
      description: 'Settings were modified by another user. The page has been refreshed.',
    })
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('save shows error for non-conflict failures', async () => {
    const user = userEvent.setup()
    mockMutate.mockImplementation((_payload: unknown, callbacks: { onError: (e: Error) => void }) => {
      callbacks.onError(new Error('network error'))
    })
    mockQueries()
    render(<Settings />)

    await user.click(screen.getByRole('button', { name: /plus/i }))
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(mockMutate).toHaveBeenCalled()
  })

  it('renders settings error state separately from categories', () => {
    vi.mocked(settingsClient.useQuery).mockImplementation((_method: string, path: string) => {
      if (path === '/settings/categories') {
        return {
          data: mockCategories,
          isPending: false,
          error: null,
          refetch: vi.fn(),
        } as never
      }
      return {
        data: undefined,
        isPending: false,
        error: null,
        refetch: vi.fn(),
      } as never
    })
    vi.mocked(useAllSettings).mockReturnValue({
      settings: [],
      isLoading: false,
      error: new Error('Settings failed'),
      refetch: vi.fn(),
    })
    render(<Settings />)

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('passes edits and callbacks to SettingsCategoryTab', async () => {
    const user = userEvent.setup()
    mockQueries()
    render(<Settings />)

    // Edit a setting to populate the edits map
    await user.click(screen.getByRole('button', { name: /plus/i }))

    // Verify the save button reflects the edit state
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()

    // Click minus to change back
    await user.click(screen.getByRole('button', { name: /minus/i }))

    // Still has edits (value changed to 4001 then 4000)
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  })

  it('reset all sets values to defaults locally', async () => {
    const user = userEvent.setup()
    mockQueries()
    render(<Settings />)

    // Edit a setting first
    await user.click(screen.getByRole('button', { name: /plus/i }))
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()

    // Reset all via modal
    await user.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    await user.click(screen.getByRole('button', { name: 'Reset all' }))

    // Save should still be enabled (local edits to default values)
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled()
  })

  describe('no access', () => {
    beforeEach(() => {
      vi.mocked(useSettingsPermissions).mockReturnValue({ canRead: false, canWrite: false })
    })

    it('shows access denied message when user cannot read', () => {
      mockQueries()
      render(<Settings />)

      expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
      expect(screen.getByText('Access denied')).toBeInTheDocument()
      expect(screen.getByText(/You don't have permission to view settings.*auditor or admin role/)).toBeInTheDocument()
      expect(screen.queryByRole('tab')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    })

    it('shows access denied when categories query returns 403', () => {
      vi.mocked(useSettingsPermissions).mockReturnValue({ canRead: true, canWrite: false })
      const forbiddenError = Object.assign(new Error('Forbidden'), { status: 403 })
      mockQueries({ error: forbiddenError })
      render(<Settings />)

      expect(screen.getByText('Access denied')).toBeInTheDocument()
      expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    })
  })

  describe('read-only mode', () => {
    beforeEach(() => {
      vi.mocked(useSettingsPermissions).mockReturnValue({ canRead: true, canWrite: false })
    })

    it('hides save button when user cannot write', () => {
      mockQueries()
      render(<Settings />)

      expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    })

    it('still displays settings categories and values', () => {
      mockQueries()
      render(<Settings />)

      expect(screen.getByRole('tab', { name: 'Context Manager' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Application' })).toBeInTheDocument()
      expect(screen.getByText('Max total tokens')).toBeInTheDocument()
    })

    it('hides reset to defaults button', () => {
      mockQueries()
      render(<Settings />)

      expect(screen.queryByRole('button', { name: 'Reset to defaults' })).not.toBeInTheDocument()
    })

    it('disables number input controls', () => {
      mockQueries()
      render(<Settings />)

      expect(screen.getByRole('spinbutton')).toBeDisabled()
    })
  })

  describe('file storage status', () => {
    it('shows permanent warning banner when S3 is unconfigured', () => {
      mockQueries()
      vi.mocked(useFileStorageStatus).mockReturnValue({
        isConfigured: false,
        isLoading: false,
        isError: false,
        status: 'unconfigured' as const,
      })

      render(<Settings />)

      expect(screen.getByText(/File uploads are disabled/)).toBeInTheDocument()
    })

    it('shows transient warning banner when S3 is degraded', () => {
      mockQueries()
      vi.mocked(useFileStorageStatus).mockReturnValue({
        isConfigured: false,
        isLoading: false,
        isError: false,
        status: 'degraded' as const,
      })

      render(<Settings />)

      expect(screen.getByText(/File uploads are temporarily unavailable/)).toBeInTheDocument()
    })

    it('shows transient warning banner when S3 has error', () => {
      mockQueries()
      vi.mocked(useFileStorageStatus).mockReturnValue({
        isConfigured: false,
        isLoading: false,
        isError: false,
        status: 'error' as const,
      })

      render(<Settings />)

      expect(screen.getByText(/File uploads are temporarily unavailable/)).toBeInTheDocument()
    })

    it('does not show warning banner when S3 is configured', () => {
      mockQueries()
      vi.mocked(useFileStorageStatus).mockReturnValue({
        isConfigured: true,
        isLoading: false,
        isError: false,
        status: 'ok' as const,
      })

      render(<Settings />)

      expect(screen.queryByText(/File uploads are disabled/)).not.toBeInTheDocument()
      expect(screen.queryByText(/File uploads are temporarily unavailable/)).not.toBeInTheDocument()
    })
  })
})
