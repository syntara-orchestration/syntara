import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { accessClient, accessFetchClient } from '../../access/accessClient'

import { CredentialsTab } from './CredentialsTab'
import type { ServiceAccountCredentialRead } from './serviceAccountTypes'

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

const mockCredentials: ServiceAccountCredentialRead[] = [
  {
    id: 'cred-1',
    service_account_id: 'sa-1',
    credential_type: 'client_credentials',
    identifier: 'client-id-abc',
    status: 'active',
    grace_period_seconds: 0,
    expires_at: null,
    last_used_at: '2024-06-15T10:00:00Z',
    created_by: 'admin',
    updated_by: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'cred-2',
    service_account_id: 'sa-1',
    credential_type: 'client_credentials',
    identifier: 'client-id-def',
    status: 'disabled',
    grace_period_seconds: 0,
    expires_at: '2025-12-31T23:59:59Z',
    last_used_at: null,
    created_by: 'admin',
    updated_by: null,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-01T00:00:00Z',
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

function buildMutationResult(mutate: ReturnType<typeof vi.fn> = vi.fn()) {
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
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

function setupMutationMocks() {
  const mocks = {
    create: vi.fn(),
    rotate: vi.fn(),
    enable: vi.fn(),
    disable: vi.fn(),
    delete: vi.fn(),
  }

  vi.mocked(accessClient.useMutation).mockImplementation(((method: string, path: string) => {
    if (method === 'post' && path.endsWith('/credentials')) return buildMutationResult(mocks.create)
    if (method === 'post' && path.includes('/rotate')) return buildMutationResult(mocks.rotate)
    if (method === 'post' && path.includes('/enable')) return buildMutationResult(mocks.enable)
    if (method === 'post' && path.includes('/disable')) return buildMutationResult(mocks.disable)
    if (method === 'delete') return buildMutationResult(mocks.delete)
    return buildMutationResult()
  }) as never)

  return mocks
}

describe('CredentialsTab', () => {
  let mockMutations: ReturnType<typeof setupMutationMocks>

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } } as never)

    for (const action of ['create', 'update', 'delete', 'rotate_secret']) {
      queryClient.setQueryData(['authz', 'can_i', { action, resource_type: 'service_account' }], {
        data: { allowed: true },
      })
    }

    vi.mocked(accessClient.useQuery).mockReturnValue(
      buildQueryResult({ resources: mockCredentials, max_lifetime_days: 180 }) as never
    )

    mockMutations = setupMutationMocks()
  })

  it('renders a table with credential data', () => {
    render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
      wrapper,
    })

    expect(screen.getByText('client-id-abc')).toBeInTheDocument()
    expect(screen.getByText('client-id-def')).toBeInTheDocument()
  })

  it('renders column headers', () => {
    render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
      wrapper,
    })

    expect(screen.getByRole('columnheader', { name: /client id/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /created/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /last used/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /expires/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /state/i })).toBeInTheDocument()
  })

  it('shows empty state when there are no credentials', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue(buildQueryResult({ resources: [] }) as never)

    render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
      wrapper,
    })

    expect(screen.getByText('No credentials yet')).toBeInTheDocument()
  })

  it('renders the Create credential button', () => {
    render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
      wrapper,
    })

    expect(screen.getByRole('button', { name: 'Create credential' })).toBeInTheDocument()
  })

  it('renders status switches for each credential', () => {
    render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
      wrapper,
    })

    expect(screen.getByRole('switch', { name: /toggle credential client-id-abc state/i })).toBeChecked()
    expect(screen.getByRole('switch', { name: /toggle credential client-id-def state/i })).not.toBeChecked()
  })

  it('shows Never for credentials without expiry date', () => {
    render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
      wrapper,
    })

    const rows = screen.getAllByRole('row')
    const firstCredRow = rows.find((row) => within(row).queryByText('client-id-abc'))
    expect(firstCredRow).toBeDefined()
    expect(within(firstCredRow!).getByText('Never')).toBeInTheDocument()
  })

  describe('Delete credential flow', () => {
    it('shows confirmation dialog when delete is triggered', async () => {
      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const kebab = screen.getByRole('button', { name: 'Actions for client-id-abc' })
      await user.click(kebab)

      const deleteOption = await screen.findByRole('menuitem', { name: /delete credential/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete credential?')).toBeInTheDocument()
      })
    })

    it('calls delete mutation when confirmation is accepted', async () => {
      mockMutations.delete.mockImplementation(
        (_params: unknown, opts: { onSuccess?: () => void; onSettled?: () => void }) => {
          opts.onSuccess?.()
          opts.onSettled?.()
        }
      )

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const kebab = screen.getByRole('button', { name: 'Actions for client-id-abc' })
      await user.click(kebab)

      const deleteOption = await screen.findByRole('menuitem', { name: /delete credential/i })
      await user.click(deleteOption)

      await waitFor(() => {
        expect(screen.getByText('Delete credential?')).toBeInTheDocument()
      })

      const ackCheckbox = screen.getByRole('checkbox', { name: /i understand/i })
      await user.click(ackCheckbox)
      await user.click(screen.getByRole('button', { name: 'Delete' }))
      expect(mockMutations.delete).toHaveBeenCalled()
    })
  })

  describe('Rotate credential flow', () => {
    it('shows confirmation dialog with grace period select when rotate is triggered', async () => {
      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const kebab = screen.getByRole('button', { name: 'Actions for client-id-abc' })
      await user.click(kebab)

      const rotateOption = await screen.findByRole('menuitem', { name: /rotate secret/i })
      await user.click(rotateOption)

      await waitFor(() => {
        expect(screen.getByText('Rotate client secret?')).toBeInTheDocument()
      })

      expect(screen.getByRole('button', { name: '1 hour' })).toBeInTheDocument()
    })

    it('calls rotate mutation with selected grace period when confirmation is accepted', async () => {
      mockMutations.rotate.mockImplementation(
        (_params: unknown, opts: { onSuccess?: (r: unknown) => void; onSettled?: () => void }) => {
          opts.onSuccess?.({ identifier: 'client-id-abc', client_secret: 'new-secret-123', grace_period_seconds: 3600 })
          opts.onSettled?.()
        }
      )

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const kebab = screen.getByRole('button', { name: 'Actions for client-id-abc' })
      await user.click(kebab)

      const rotateOption = await screen.findByRole('menuitem', { name: /rotate secret/i })
      await user.click(rotateOption)

      await waitFor(() => {
        expect(screen.getByText('Rotate client secret?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Rotate secret' }))
      expect(mockMutations.rotate).toHaveBeenCalled()

      const callArgs = mockMutations.rotate.mock.calls[0] as [{ body: { grace_period_seconds: number } }]
      expect(callArgs[0].body.grace_period_seconds).toBe(3600)

      await waitFor(() => {
        expect(screen.getByText('New client secret')).toBeInTheDocument()
      })
    })

    it('sends selected grace period when a non-default option is chosen', async () => {
      mockMutations.rotate.mockImplementation(
        (_params: unknown, opts: { onSuccess?: (r: unknown) => void; onSettled?: () => void }) => {
          opts.onSuccess?.({
            identifier: 'client-id-abc',
            client_secret: 'new-secret-456',
            grace_period_seconds: 86400,
          })
          opts.onSettled?.()
        }
      )

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" resourceProject="proj-1" />, { wrapper })

      const kebab = screen.getByRole('button', { name: 'Actions for client-id-abc' })
      await user.click(kebab)

      const rotateOption = await screen.findByRole('menuitem', { name: /rotate secret/i })
      await user.click(rotateOption)

      await waitFor(() => {
        expect(screen.getByText('Rotate client secret?')).toBeInTheDocument()
      })

      const gracePeriodToggle = screen.getByRole('button', { name: '1 hour' })
      await user.click(gracePeriodToggle)

      const option24h = await screen.findByRole('option', { name: '24 hours' })
      await user.click(option24h)

      await user.click(screen.getByRole('button', { name: 'Rotate secret' }))

      const callArgs = mockMutations.rotate.mock.calls[0] as [{ body: { grace_period_seconds: number } }]
      expect(callArgs[0].body.grace_period_seconds).toBe(86400)
    })

    it('shows active grace period warning when credential has old_secret_valid_until', async () => {
      const futureDate = new Date(Date.now() + 3_600_000).toISOString()
      const credsWithGracePeriod: ServiceAccountCredentialRead[] = [
        {
          ...mockCredentials[0],
          old_secret_valid_until: futureDate,
          grace_period_seconds: 3600,
        },
      ]
      vi.mocked(accessClient.useQuery).mockReturnValue(buildQueryResult({ resources: credsWithGracePeriod }) as never)

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" resourceProject="proj-1" />, { wrapper })

      const kebab = screen.getByRole('button', { name: 'Actions for client-id-abc' })
      await user.click(kebab)

      const rotateOption = await screen.findByRole('menuitem', { name: /rotate secret/i })
      await user.click(rotateOption)

      await waitFor(() => {
        expect(screen.getByText('Active grace period will be replaced')).toBeInTheDocument()
      })
    })
  })

  describe('Disable credential flow', () => {
    it('shows confirmation dialog when toggling an active credential', async () => {
      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const toggle = screen.getByRole('switch', { name: /toggle credential client-id-abc state/i })
      await user.click(toggle)

      await waitFor(() => {
        expect(screen.getByText('Disable credential?')).toBeInTheDocument()
      })
    })

    it('calls disable mutation when confirmation is accepted', async () => {
      mockMutations.disable.mockImplementation(
        (_params: unknown, opts: { onSuccess?: () => void; onSettled?: () => void }) => {
          opts.onSuccess?.()
          opts.onSettled?.()
        }
      )

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const toggle = screen.getByRole('switch', { name: /toggle credential client-id-abc state/i })
      await user.click(toggle)

      await waitFor(() => {
        expect(screen.getByText('Disable credential?')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Disable' }))
      expect(mockMutations.disable).toHaveBeenCalled()
    })

    it('enables a disabled credential directly without confirmation', async () => {
      mockMutations.enable.mockImplementation((_params: unknown, opts: { onSuccess?: () => void }) => {
        opts.onSuccess?.()
      })

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const toggle = screen.getByRole('switch', { name: /toggle credential client-id-def state/i })
      await user.click(toggle)

      expect(mockMutations.enable).toHaveBeenCalled()
    })
  })

  describe('Create credential flow', () => {
    it('opens create credential modal when button is clicked', async () => {
      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Create credential' }))

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Create credential' })).toBeInTheDocument()
      })
      expect(screen.getByText('Expiration date')).toBeInTheDocument()
    })

    it('calls create mutation with expires_at and shows secret when successful', async () => {
      mockMutations.create.mockImplementation((_params: unknown, opts: { onSuccess?: (r: unknown) => void }) => {
        opts.onSuccess?.({
          identifier: 'new-client-id',
          client_secret: 'super-secret',
          expires_at: '2025-12-31T00:00:00Z',
        })
      })

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      await user.click(screen.getByRole('button', { name: 'Create credential' }))

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Create credential' })).toBeInTheDocument()
      })

      const createButton = screen.getByRole('button', { name: 'Create' })
      await user.click(createButton)

      expect(mockMutations.create).toHaveBeenCalled()

      await waitFor(() => {
        expect(screen.getByText('New credential created')).toBeInTheDocument()
      })
    })

    it('disables Create credential button when at max credentials', () => {
      const maxCreds = Array.from({ length: 10 }, (_, i) => ({
        ...mockCredentials[0],
        id: `cred-${i}`,
        identifier: `client-id-${i}`,
      }))

      vi.mocked(accessClient.useQuery).mockReturnValue(
        buildQueryResult({ resources: maxCreds, max_credentials: 10, total_credentials: 10 }) as never
      )

      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const createButton = screen.getByRole('button', { name: 'Create credential' })
      expect(createButton).toHaveAttribute('aria-disabled', 'true')
    })

    it('shows tooltip with limit message when at max credentials', async () => {
      const maxCreds = Array.from({ length: 10 }, (_, i) => ({
        ...mockCredentials[0],
        id: `cred-${i}`,
        identifier: `client-id-${i}`,
      }))

      vi.mocked(accessClient.useQuery).mockReturnValue(
        buildQueryResult({ resources: maxCreds, max_credentials: 10, total_credentials: 10 }) as never
      )

      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const createButton = screen.getByRole('button', { name: 'Create credential' })
      await user.hover(createButton)

      await waitFor(() => {
        expect(screen.getByText('deploy-bot has reached the maximum of 10 credentials')).toBeInTheDocument()
      })
    })
  })

  describe('Filtering', () => {
    it('shows dash for credentials with no last used date', () => {
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const rows = screen.getAllByRole('row')
      const secondCredRow = rows.find((row) => within(row).queryByText('client-id-def'))
      expect(secondCredRow).toBeDefined()
      expect(within(secondCredRow!).getByText('-')).toBeInTheDocument()
    })

    it('passes status filter to the API query', async () => {
      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const statusToggle = screen.getByRole('button', { name: 'Filter by status' })
      await user.click(statusToggle)

      const enabledOption = await screen.findByRole('option', { name: 'Enabled' })
      await user.click(enabledOption)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params: { query: Record<string, unknown> } } | undefined)
          ?.params?.query
        expect(queryParams).toMatchObject({ status: 'active' })
      })
    })

    it('clears filters when clear all is clicked', async () => {
      const user = userEvent.setup()
      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      const statusToggle = screen.getByRole('button', { name: 'Filter by status' })
      await user.click(statusToggle)

      const enabledOption = await screen.findByRole('option', { name: 'Enabled' })
      await user.click(enabledOption)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params: { query: Record<string, unknown> } } | undefined)
          ?.params?.query
        expect(queryParams).toMatchObject({ status: 'active' })
      })

      const clearButton = screen.getByRole('button', { name: /clear all filters/i })
      await user.click(clearButton)

      await waitFor(() => {
        const lastCall = vi.mocked(accessClient.useQuery).mock.calls.at(-1)
        const queryParams = (lastCall?.[2] as unknown as { params: { query: Record<string, unknown> } } | undefined)
          ?.params?.query
        expect(queryParams).not.toHaveProperty('status')
      })
    })
  })

  describe('Error handling', () => {
    it('renders error state when query fails', () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(
        buildQueryResult(undefined, {
          isError: true,
          isPending: false,
          isSuccess: false,
          error: new Error('Network error'),
          data: undefined,
        }) as never
      )

      render(<CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />, {
        wrapper,
      })

      expect(screen.getByRole('heading', { name: 'Error loading credentials' })).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with credentials table', async () => {
      const { container } = render(
        <CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />,
        {
          wrapper,
        }
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations when at max credentials', async () => {
      const maxCreds = Array.from({ length: 10 }, (_, i) => ({
        ...mockCredentials[0],
        id: `cred-${i}`,
        identifier: `client-id-${i}`,
      }))

      vi.mocked(accessClient.useQuery).mockReturnValue(
        buildQueryResult({ resources: maxCreds, max_credentials: 10, total_credentials: 10 }) as never
      )

      const { container } = render(
        <CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />,
        {
          wrapper,
        }
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations in empty state', async () => {
      vi.mocked(accessClient.useQuery).mockReturnValue(buildQueryResult({ resources: [] }) as never)

      const { container } = render(
        <CredentialsTab serviceAccountId="sa-1" serviceAccountName="deploy-bot" resourceProject="proj-1" />,
        {
          wrapper,
        }
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
