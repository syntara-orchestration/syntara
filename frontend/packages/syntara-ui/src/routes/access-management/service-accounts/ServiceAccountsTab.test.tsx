import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'
import { accessClient } from '../../access/accessClient'

import { ServiceAccountsTab } from './ServiceAccountsTab'
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

vi.mock('./CreateServiceAccountModal', () => ({
  CreateServiceAccountModal: () => <div data-testid="create-sa-modal" />,
}))

vi.mock('./EditServiceAccountModal', () => ({
  EditServiceAccountModal: () => <div role="dialog" aria-label="Edit service account" />,
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockServiceAccounts: ServiceAccountRead[] = [
  {
    id: 'sa-1',
    name: 'deploy-bot',
    description: 'Deployment automation',
    status: 'active',
    project_id: 'proj-1',
    project_name: 'default',
    is_project_deleted: false,
    last_authenticated_at: '2024-06-15T10:00:00Z',
    created_by: 'admin',
    updated_by: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    labels: {},
  },
  {
    id: 'sa-2',
    name: 'ci-runner',
    description: null,
    status: 'disabled',
    project_id: 'proj-1',
    project_name: 'default',
    is_project_deleted: false,
    last_authenticated_at: null,
    created_by: 'admin',
    updated_by: null,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-01T00:00:00Z',
    labels: {},
  },
]

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

describe('ServiceAccountsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerTestState.pathname = '/system-administration/access-management/service-accounts'

    vi.mocked(useServiceAccountPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: true,
      canDelete: true,
      canRotateSecret: true,
      isLoading: false,
      isError: false,
      tooltips: { create: '', update: '', delete: '', rotateSecret: '' },
    })

    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ resources: mockServiceAccounts, next_cursor: null }) as never
    )

    vi.mocked(accessClient.useMutation).mockReturnValue(buildMutationResult() as never)
  })

  it('renders service accounts in a table', () => {
    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByText('deploy-bot')).toBeInTheDocument()
    expect(screen.getByText('ci-runner')).toBeInTheDocument()
  })

  it('renders table column headers', () => {
    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByRole('columnheader', { name: /name/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /owning project/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /created/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /last authenticated/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /state/i })).toBeInTheDocument()
  })

  it('renders owning project as a link when project exists', () => {
    render(<ServiceAccountsTab />, { wrapper })

    const links = screen.getAllByRole('link', { name: 'default' })
    expect(links.length).toBeGreaterThanOrEqual(1)
    expect(links[0]).toHaveAttribute('href', '/system-administration/access-management/projects/proj-1')
  })

  it('renders owning project as plain text with Deleted label when project is deleted', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({
        resources: [{ ...mockServiceAccounts[0], project_name: 'old-project', is_project_deleted: true }],
        next_cursor: null,
      }) as never
    )

    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByText('old-project')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'old-project' })).not.toBeInTheDocument()
    expect(screen.getByText('Deleted')).toBeInTheDocument()
  })

  it('renders owning project as project ID when project_name is null', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({
        resources: [{ ...mockServiceAccounts[0], project_name: null }],
        next_cursor: null,
      }) as never
    )

    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByText('proj-1')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'proj-1' })).not.toBeInTheDocument()
  })

  it('shows Create service account button', () => {
    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByRole('button', { name: 'Create service account' })).toBeInTheDocument()
  })

  it('renders empty state when no service accounts exist', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(buildQueryResult({ resources: [], next_cursor: null }) as never)

    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByText('No service accounts yet')).toBeInTheDocument()
  })

  it('renders service account name as a link', () => {
    render(<ServiceAccountsTab />, { wrapper })

    const link = screen.getByRole('link', { name: 'deploy-bot' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', expect.stringContaining('sa-1'))
  })

  it('shows kebab actions for each row', async () => {
    const user = userEvent.setup()
    render(<ServiceAccountsTab />, { wrapper })

    const kebab = screen.getByRole('button', { name: 'Actions for deploy-bot' })
    await user.click(kebab)

    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: /edit/i })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: /delete/i })).toBeInTheDocument()
    })
  })

  it('shows delete confirmation dialog when delete action is triggered', async () => {
    const user = userEvent.setup()
    render(<ServiceAccountsTab />, { wrapper })

    const kebab = screen.getByRole('button', { name: 'Actions for deploy-bot' })
    await user.click(kebab)

    const deleteAction = await screen.findByRole('menuitem', { name: /delete/i })
    await user.click(deleteAction)

    await waitFor(() => {
      expect(screen.getByText('Delete service account?')).toBeInTheDocument()
    })
  })

  it('renders status switches for each service account', () => {
    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByRole('switch', { name: /toggle deploy-bot status/i })).toBeChecked()
    expect(screen.getByRole('switch', { name: /toggle ci-runner status/i })).not.toBeChecked()
  })

  it('shows disable confirmation dialog when toggling an enabled account', async () => {
    const user = userEvent.setup()
    render(<ServiceAccountsTab />, { wrapper })

    const toggle = screen.getByRole('switch', { name: /toggle deploy-bot status/i })
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
    render(<ServiceAccountsTab />, { wrapper })

    const toggle = screen.getByRole('switch', { name: /toggle deploy-bot status/i })
    await user.click(toggle)

    await waitFor(() => {
      expect(screen.getByText('Disable service account?')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Disable service account' }))
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

    const user = userEvent.setup()
    render(<ServiceAccountsTab />, { wrapper })

    const toggle = screen.getByRole('switch', { name: /toggle ci-runner status/i })
    await user.click(toggle)

    expect(mockEnableMutate).toHaveBeenCalled()
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
    render(<ServiceAccountsTab />, { wrapper })

    const kebab = screen.getByRole('button', { name: 'Actions for deploy-bot' })
    await user.click(kebab)

    const deleteAction = await screen.findByRole('menuitem', { name: /delete/i })
    await user.click(deleteAction)

    await waitFor(() => {
      expect(screen.getByText('Delete service account?')).toBeInTheDocument()
    })

    const ackCheckbox = screen.getByRole('checkbox', { name: /i understand/i })
    await user.click(ackCheckbox)
    await user.click(screen.getByRole('button', { name: 'Delete service account' }))
    expect(mockDeleteMutate).toHaveBeenCalled()
  })

  it('opens edit modal when edit action is clicked', async () => {
    const user = userEvent.setup()
    render(<ServiceAccountsTab />, { wrapper })

    const kebab = screen.getByRole('button', { name: 'Actions for deploy-bot' })
    await user.click(kebab)

    const editAction = await screen.findByRole('menuitem', { name: /edit/i })
    await user.click(editAction)

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Edit service account' })).toBeInTheDocument()
    })
  })

  it('renders description text above the table', () => {
    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByText(/service accounts provide programmatic access/i)).toBeInTheDocument()
  })

  it('disables toggle switches when canUpdate is false', () => {
    vi.mocked(useServiceAccountPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: false,
      canDelete: true,
      canRotateSecret: true,
      isLoading: false,
      isError: false,
      tooltips: { create: '', update: 'Insufficient permissions', delete: '', rotateSecret: '' },
    })

    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByRole('switch', { name: /toggle deploy-bot status/i })).toBeDisabled()
    expect(screen.getByRole('switch', { name: /toggle ci-runner status/i })).toBeDisabled()
  })

  it('disables Create service account button when canCreate is false', () => {
    vi.mocked(useServiceAccountPermissions).mockReturnValue({
      canCreate: false,
      canUpdate: true,
      canDelete: true,
      canRotateSecret: true,
      isLoading: false,
      isError: false,
      tooltips: { create: 'Insufficient permissions', update: '', delete: '', rotateSecret: '' },
    })

    render(<ServiceAccountsTab />, { wrapper })

    expect(screen.getByRole('button', { name: 'Create service account' })).toHaveAttribute('aria-disabled', 'true')
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
    render(<ServiceAccountsTab />, { wrapper })

    const kebab = screen.getByRole('button', { name: 'Actions for deploy-bot' })
    await user.click(kebab)

    const deleteAction = await screen.findByRole('menuitem', { name: /delete/i })
    expect(deleteAction).toHaveAttribute('aria-disabled', 'true')
  })

  it('disables edit action in kebab menu when canUpdate is false', async () => {
    vi.mocked(useServiceAccountPermissions).mockReturnValue({
      canCreate: true,
      canUpdate: false,
      canDelete: true,
      canRotateSecret: true,
      isLoading: false,
      isError: false,
      tooltips: { create: '', update: 'Insufficient permissions', delete: '', rotateSecret: '' },
    })

    const user = userEvent.setup()
    render(<ServiceAccountsTab />, { wrapper })

    const kebab = screen.getByRole('button', { name: 'Actions for deploy-bot' })
    await user.click(kebab)

    const editAction = await screen.findByRole('menuitem', { name: /edit/i })
    expect(editAction).toHaveAttribute('aria-disabled', 'true')
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with service accounts table', async () => {
      const { container } = render(<ServiceAccountsTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(buildQueryResult({ resources: [], next_cursor: null }) as never)

      const { container } = render(<ServiceAccountsTab />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
