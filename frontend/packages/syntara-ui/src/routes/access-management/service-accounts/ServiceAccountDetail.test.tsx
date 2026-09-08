import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useParams } from '@tanstack/react-router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../../app/AppRoute'
import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'
import { accessClient } from '../../access/accessClient'

import { ServiceAccountDetail } from './ServiceAccountDetail'
import type { ServiceAccountRead } from './serviceAccountTypes'
import { useServiceAccountPermissions } from './useServiceAccountPermissions'

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

vi.mock('./useServiceAccountPermissions')

vi.mock('./CredentialsTab', () => ({
  CredentialsTab: () => <div data-testid="credentials-tab" />,
}))

vi.mock('./EditServiceAccountModal', () => ({
  EditServiceAccountModal: () => <div role="dialog" aria-label="Edit service account" />,
}))

const mockServiceAccount: ServiceAccountRead = {
  id: 'sa-1',
  name: 'deploy-bot',
  description: 'Deployment automation account',
  status: 'active',
  project_id: 'proj-1',
  last_authenticated_at: '2024-06-15T10:00:00Z',
  created_by: 'admin',
  updated_by: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  labels: {},
}

function buildQueryResult(data: unknown, overrides: Record<string, unknown> = {}) {
  return {
    data,
    isLoading: false,
    isPending: false,
    isError: false,
    error: null,
    isFetching: false,
    isSuccess: true,
    refetch: vi.fn().mockResolvedValue({ data }),
    ...overrides,
  }
}

function buildMutationResult(mutate = vi.fn()) {
  return {
    mutate,
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
    status: 'idle' as const,
    isPaused: false,
  }
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('ServiceAccountDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerTestState.pathname = '/system-administration/access-management/service-accounts/sa-1/details'
    vi.mocked(useParams).mockReturnValue({ serviceAccountId: 'sa-1' })

    vi.mocked(useServiceAccountPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      canRotateSecret: true,
      isLoading: false,
      isError: false,
      tooltips: { create: '', update: '', delete: '', rotateSecret: '' },
    })

    vi.mocked(accessClient.useQuery).mockReturnValue(buildQueryResult(mockServiceAccount) as never)

    vi.mocked(accessClient.useMutation).mockReturnValue(buildMutationResult() as never)
  })

  it('renders the service account name as heading', () => {
    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByRole('heading', { name: 'deploy-bot' })).toBeInTheDocument()
  })

  it('renders outline enabled state label on details tab', () => {
    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('Enabled', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
  })

  it('renders details tab content by default', () => {
    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('Deployment automation account')).toBeInTheDocument()
    expect(screen.getAllByText('Enabled').length).toBeGreaterThanOrEqual(1)
  })

  it('renders tab navigation with Details, Credentials, and Assignments tabs', () => {
    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByRole('tab', { name: 'Details' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Credentials' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Assignments' })).toBeInTheDocument()
  })

  it('renders the toolbar with Edit button and kebab menu', () => {
    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByRole('button', { name: 'Edit service account' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Service account actions' })).toBeInTheDocument()
  })

  it('renders the status toggle switch', () => {
    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByRole('switch', { name: 'Toggle service account status' })).toBeChecked()
  })

  it('shows delete confirmation dialog when Delete is clicked from kebab', async () => {
    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Service account actions' }))
    const deleteOption = await screen.findByRole('menuitem', { name: /delete service account/i })
    await user.click(deleteOption)

    await waitFor(() => {
      expect(screen.getByText('Delete service account?')).toBeInTheDocument()
    })
  })

  it('shows disable confirmation dialog when toggling an enabled account', async () => {
    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    const toggle = screen.getByRole('switch', { name: 'Toggle service account status' })
    await user.click(toggle)

    await waitFor(() => {
      expect(screen.getByText('Disable service account?')).toBeInTheDocument()
    })
  })

  it('calls disable mutation when disable dialog is confirmed', async () => {
    const mockDisableMutate = vi
      .fn()
      .mockImplementation((_params: unknown, opts: { onSuccess?: () => void; onSettled?: () => void }) => {
        opts.onSuccess?.()
        opts.onSettled?.()
      })
    vi.mocked(accessClient.useMutation).mockImplementation(((method: string, path: string) => {
      if (method === 'post' && path.includes('/disable')) {
        return buildMutationResult(mockDisableMutate)
      }
      return buildMutationResult()
    }) as never)

    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    const toggle = screen.getByRole('switch', { name: 'Toggle service account status' })
    await user.click(toggle)

    await waitFor(() => {
      expect(screen.getByText('Disable service account?')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Disable' }))
    expect(mockDisableMutate).toHaveBeenCalled()
  })

  it('enables a disabled account directly without confirmation', async () => {
    const mockEnableMutate = vi.fn().mockImplementation((_params: unknown, opts: { onSuccess?: () => void }) => {
      opts.onSuccess?.()
    })
    vi.mocked(accessClient.useMutation).mockImplementation(((method: string, path: string) => {
      if (method === 'post' && path.includes('/enable')) {
        return buildMutationResult(mockEnableMutate)
      }
      return buildMutationResult()
    }) as never)

    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, status: 'disabled' }) as never
    )

    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    const toggle = screen.getByRole('switch', { name: 'Toggle service account status' })
    await user.click(toggle)

    expect(mockEnableMutate).toHaveBeenCalled()
  })

  it('opens edit modal when Edit button is clicked', async () => {
    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Edit service account' }))

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Edit service account' })).toBeInTheDocument()
    })
  })

  it('renders not-found state when query errors', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult(undefined, {
        isError: true,
        error: new Error('Not found'),
        data: undefined,
      }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('Service account not found')).toBeInTheDocument()
  })

  it('renders retry button in not-found state', async () => {
    const mockRefetch = vi.fn().mockResolvedValue({ data: mockServiceAccount })
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult(undefined, {
        isError: true,
        error: new Error('Not found'),
        data: undefined,
        refetch: mockRefetch,
      }) as never
    )

    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    const retryButton = screen.getByRole('button', { name: /retry/i })
    await user.click(retryButton)

    expect(mockRefetch).toHaveBeenCalled()
  })

  it('shows outline disabled state label on details tab', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, status: 'disabled' }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('Disabled', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
  })

  it('shows Disabled state for disabled service accounts', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, status: 'disabled' }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getAllByText('Disabled').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('switch', { name: 'Toggle service account status' })).not.toBeChecked()
  })

  it('renders owning project as a link when project_name is present', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, project_name: 'my-project', is_project_deleted: false }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    const link = screen.getByRole('link', { name: 'my-project' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/system-administration/access-management/projects/proj-1')
  })

  it('renders owning project as plain text when project_name is null', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, project_name: null }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('proj-1')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'proj-1' })).not.toBeInTheDocument()
  })

  it('renders owning project as plain text with Deleted label when project is deleted', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, project_name: 'old-project', is_project_deleted: true }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('old-project')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'old-project' })).not.toBeInTheDocument()
    expect(screen.getByText('Deleted')).toBeInTheDocument()
  })

  it('shows Never for last authenticated when never used', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, last_authenticated_at: null }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('Never')).toBeInTheDocument()
  })

  it('shows assignments tab when navigated to', () => {
    routerTestState.pathname = '/system-administration/access-management/service-accounts/sa-1/assignments'

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('No role assignments yet')).toBeInTheDocument()
  })

  it('calls delete mutation when delete dialog is confirmed', async () => {
    const mockDeleteMutate = vi
      .fn()
      .mockImplementation((_params: unknown, opts: { onSuccess?: () => void; onSettled?: () => void }) => {
        opts.onSuccess?.()
        opts.onSettled?.()
      })
    vi.mocked(accessClient.useMutation).mockImplementation(((method: string) => {
      if (method === 'delete') {
        return buildMutationResult(mockDeleteMutate)
      }
      return buildMutationResult()
    }) as never)

    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Service account actions' }))
    const deleteOption = await screen.findByRole('menuitem', { name: /delete service account/i })
    await user.click(deleteOption)

    await waitFor(() => {
      expect(screen.getByText('Delete service account?')).toBeInTheDocument()
    })

    const ackCheckbox = screen.getByRole('checkbox', { name: /i understand/i })
    await user.click(ackCheckbox)
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(mockDeleteMutate).toHaveBeenCalled()
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: AppRoute.AccessManagement.ServiceAccounts })
  })

  it('renders loading state while query is pending', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult(undefined, {
        isPending: true,
        isLoading: true,
        isSuccess: false,
        data: undefined,
      }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByText('Service Account Details')).toBeInTheDocument()
  })

  it('hides description row when description is null', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ ...mockServiceAccount, description: null }) as never
    )

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.queryByText('Description')).not.toBeInTheDocument()
  })

  it('disables edit and toggle controls when canUpdate is false', () => {
    vi.mocked(useServiceAccountPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: false,
      canDelete: true,
      canRotateSecret: true,
      isLoading: false,
      isError: false,
      tooltips: { create: '', update: 'Insufficient permissions', delete: '', rotateSecret: '' },
    })

    render(<ServiceAccountDetail />, { wrapper })

    expect(screen.getByRole('button', { name: 'Edit service account' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('switch', { name: 'Toggle service account status' })).toBeDisabled()
  })

  it('disables delete action in kebab menu when canDelete is false', async () => {
    vi.mocked(useServiceAccountPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: true,
      canDelete: false,
      canRotateSecret: true,
      isLoading: false,
      isError: false,
      tooltips: { create: '', update: '', delete: 'Insufficient permissions', rotateSecret: '' },
    })

    const user = userEvent.setup()
    render(<ServiceAccountDetail />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Service account actions' }))
    const deleteOption = await screen.findByRole('menuitem', { name: /delete service account/i })

    expect(deleteOption).toHaveAttribute('aria-disabled', 'true')
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<ServiceAccountDetail />, { wrapper })

      // Exclude aria-valid-attr-value: PatternFly Tabs generates aria-controls
      // referencing panel IDs not in the DOM when panels are conditionally rendered.
      const results = await axe(container, {
        rules: { 'aria-valid-attr-value': { enabled: false } },
      })
      expect(results).toHaveNoViolations()
    })
  })
})
