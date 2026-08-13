import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useParams } from '@tanstack/react-router'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { usersClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'

import { TransferIdentityWizard } from './TransferIdentityWizard'

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
  usersClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

const mockAccessClientUseQuery = vi.fn()
vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: (...args: unknown[]): unknown => mockAccessClientUseQuery(...args),
  },
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const React = await import('react')
  // Import global setup's router mock
  const { routerTestState } = await import('../../../test/setup')
  return {
    ...actual,
    Link: ({
      to,
      children,
      className,
      style,
      ...rest
    }: {
      to: string
      children: React.ReactNode
      className?: string
      style?: React.CSSProperties
    }) => React.createElement('a', { href: String(to), className, style, ...rest }, children),
    useParams: vi.fn(() => ({ userId: 'target-user' })),
    useNavigate: () => routerTestState.navigate,
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const state = { location: { pathname: routerTestState.pathname, searchStr: routerTestState.searchStr } }
      return opts?.select ? opts.select(state) : state
    },
    useRouter: () => ({
      history: { push: routerTestState.historyPush },
      state: { location: { pathname: routerTestState.pathname, searchStr: routerTestState.searchStr } },
    }),
    useBlocker: () => ({ status: 'idle' }),
    useMatch: vi.fn(() => ({ params: {} })),
  }
})

vi.mock('../../../hooks/routing/Link', () => ({
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [key: string]: unknown }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock('../../../utils/generateUUID', () => ({
  isValidUUID: () => true,
}))

vi.mock('./TransferIdentityWizard.module.css', () => ({ default: {} }))

const mockUsers = {
  resources: [
    { id: 'user-1', username: 'alice', email: 'alice@example.com', first_name: 'Alice', last_name: 'Smith' },
    { id: 'user-2', username: 'bob', email: 'bob@example.com', first_name: 'Bob', last_name: 'Jones' },
    { id: 'target-user', username: 'targetuser', email: 'target@example.com', first_name: 'Target', last_name: 'User' },
  ],
  next: null,
  total: 3,
}

const mockIdentities = [
  {
    id: 'id-1',
    user_id: 'user-2',
    identity_provider_id: 'p-1',
    issuer: 'https://idp.example.com',
    subject: 'sub-1',
    created_at: '2026-01-01T00:00:00Z',
    provider_name: 'Azure',
  },
]

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AlertProvider>{children}</AlertProvider>
    </QueryClientProvider>
  )
}

let mockMutate: ReturnType<typeof vi.fn>

function setupAccessClientMock() {
  mockAccessClientUseQuery.mockReturnValue({
    data: {
      id: 'target-user',
      username: 'targetuser',
      first_name: 'Target',
      last_name: 'User',
      email: 'target@example.com',
      is_enabled: true,
      auth_type: 'federated',
    },
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  })
}

function setupMocks({
  identities = mockIdentities,
  users = mockUsers,
  emptyUsersWhenFiltered = false,
}: {
  identities?: unknown[]
  users?: typeof mockUsers
  emptyUsersWhenFiltered?: boolean
} = {}) {
  vi.mocked(usersClient.useQuery).mockImplementation((_method, path, options) => {
    if (path === '/users') {
      const query = (options as { params?: { query?: Record<string, unknown> } } | undefined)?.params?.query ?? {}
      const hasApiFilters = Object.keys(query).some(
        (key) => key !== 'limit' && key !== 'include_total' && key !== 'cursor'
      )
      const data = emptyUsersWhenFiltered && hasApiFilters ? { resources: [], next: null, total: 0 } : users
      return {
        data,
        isPending: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      } as never
    }
    return {
      data: { resources: identities, next: null, prev: null, total: identities.length },
      isPending: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never
  })

  mockMutate = vi.fn()
  vi.mocked(usersClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
  } as never)
}

describe('TransferIdentityWizard', () => {
  beforeEach(() => {
    queryClient.clear()
    vi.mocked(useParams).mockReturnValue({ userId: 'target-user' })
    setupAccessClientMock()
    setupMocks()
  })

  it('renders the page header with username in title', () => {
    render(<TransferIdentityWizard />, { wrapper })

    expect(screen.getByRole('heading', { name: /Transfer identity to targetuser/i })).toBeInTheDocument()
  })

  it('renders the description text with username', () => {
    render(<TransferIdentityWizard />, { wrapper })

    expect(screen.getByText(/Transfer a federated identity from another user to/i)).toBeInTheDocument()
  })

  it('renders the wizard step navigation', () => {
    render(<TransferIdentityWizard />, { wrapper })

    const nav = screen.getByRole('navigation', { name: /wizard/i })
    expect(nav).toBeInTheDocument()
    expect(screen.getAllByText('Select a user').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Select an identity').length).toBeGreaterThan(0)
  })

  describe('Step 1 - Select a user', () => {
    it('shows users table excluding the target user', () => {
      render(<TransferIdentityWizard />, { wrapper })

      expect(screen.getByText('alice')).toBeInTheDocument()
      expect(screen.getByText('bob')).toBeInTheDocument()
      expect(screen.queryByRole('cell', { name: 'targetuser' })).not.toBeInTheDocument()
    })

    it('renders Username and Email column headers', () => {
      render(<TransferIdentityWizard />, { wrapper })

      expect(screen.getByRole('columnheader', { name: /Username/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Email/i })).toBeInTheDocument()
    })

    it('shows step description text', () => {
      render(<TransferIdentityWizard />, { wrapper })

      expect(screen.getByText(/Choose the user whose federated identity you want to transfer/i)).toBeInTheDocument()
    })

    it('has Next button disabled until a user is selected', async () => {
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })

      expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()

      await user.click(screen.getByText('alice@example.com'))

      expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
    })

    it('has Back button visible but disabled on step 1', () => {
      render(<TransferIdentityWizard />, { wrapper })

      const backButton = screen.getByRole('button', { name: 'Back' })
      expect(backButton).toBeInTheDocument()
      expect(backButton).toBeDisabled()
    })

    it('shows radio buttons for single selection', () => {
      render(<TransferIdentityWizard />, { wrapper })

      const radios = screen.getAllByRole('radio')
      expect(radios.length).toBeGreaterThan(0)
    })

    it('shows no-data empty state when no selectable users exist', () => {
      setupMocks({
        users: {
          resources: [
            {
              id: 'target-user',
              username: 'targetuser',
              email: 'target@example.com',
              first_name: 'Target',
              last_name: 'User',
            },
          ],
          next: null,
          total: 1,
        },
      })
      render(<TransferIdentityWizard />, { wrapper })

      expect(screen.getByText('No users yet')).toBeInTheDocument()
      expect(
        screen.getByText('There must be at least one other user before you can transfer a federated identity.')
      ).toBeInTheDocument()
      expect(
        screen.queryByText(/Choose the user whose federated identity you want to transfer/i)
      ).not.toBeInTheDocument()
      expect(screen.queryByRole('search', { name: 'Filters' })).not.toBeInTheDocument()
      expect(screen.queryByRole('columnheader', { name: /Username/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('columnheader', { name: /Email/i })).not.toBeInTheDocument()
    })

    it('shows filter empty state when no users match active filters', async () => {
      setupMocks({ emptyUsersWhenFiltered: true })
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })

      const usernameInput = screen.getByRole('textbox', { name: /username filter/i })
      await user.type(usernameInput, 'zzz-nonexistent')
      await user.keyboard('{Enter}')

      expect(await screen.findByText('No results found')).toBeInTheDocument()
      expect(screen.getByText(/Choose the user whose federated identity you want to transfer/i)).toBeInTheDocument()
      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
      expect(screen.queryByText('No users yet')).not.toBeInTheDocument()
    })
  })

  describe('Step 2 - Select an identity', () => {
    async function goToStep2() {
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })
      await user.click(screen.getByText('bob@example.com'))
      await user.click(screen.getByRole('button', { name: 'Next' }))
      return user
    }

    it('shows identity table with Provider, Subject, Linked columns', async () => {
      await goToStep2()

      expect(screen.getByRole('columnheader', { name: /Provider/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Subject/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Linked/i })).toBeInTheDocument()
      expect(screen.getByText('Azure')).toBeInTheDocument()
      expect(screen.getByText('sub-1')).toBeInTheDocument()
    })

    it('shows step 2 description with selected user full name', async () => {
      await goToStep2()

      expect(screen.getByText(/Choose one of/i)).toBeInTheDocument()
      expect(screen.getAllByText(/Bob Jones/i).length).toBeGreaterThan(0)
    })

    it('shows empty state when selected user has no identities', async () => {
      setupMocks({ identities: [] })
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })

      await user.click(screen.getByText('bob@example.com'))
      await user.click(screen.getByRole('button', { name: 'Next' }))

      expect(screen.getByText('No identities')).toBeInTheDocument()
      expect(screen.getByText('This user has no federated identities to attach.')).toBeInTheDocument()
      expect(screen.queryByRole('heading', { level: 2, name: 'Select an identity' })).not.toBeInTheDocument()
      expect(screen.queryByText(/Choose one of/i)).not.toBeInTheDocument()
      expect(screen.queryByRole('search', { name: 'Filters' })).not.toBeInTheDocument()
      expect(screen.queryByRole('columnheader', { name: /Provider/i })).not.toBeInTheDocument()
    })

    it('shows filter empty state when no identities match active filters', async () => {
      const user = await goToStep2()

      const providerInput = screen.getByRole('textbox', { name: /provider filter/i })
      await user.type(providerInput, 'zzz-nonexistent')
      await user.keyboard('{Enter}')

      expect(await screen.findByText('No results found')).toBeInTheDocument()
      expect(screen.getByText(/Choose one of/i)).toBeInTheDocument()
      expect(screen.getByRole('search', { name: 'Filters' })).toBeInTheDocument()
      expect(screen.queryByText('No identities')).not.toBeInTheDocument()
    })

    it('has Transfer identity button disabled until an identity is selected', async () => {
      const user = await goToStep2()

      expect(screen.getByRole('button', { name: 'Transfer identity' })).toBeDisabled()

      await user.click(screen.getByText('sub-1'))

      expect(screen.getByRole('button', { name: 'Transfer identity' })).toBeEnabled()
    })

    it('deselects identity when clicking a selected row again', async () => {
      const user = await goToStep2()

      await user.click(screen.getByText('sub-1'))
      expect(screen.getByRole('button', { name: 'Transfer identity' })).toBeEnabled()

      await user.click(screen.getByText('sub-1'))
      expect(screen.getByRole('button', { name: 'Transfer identity' })).toBeDisabled()
    })

    it('calls mutation with correct params when Transfer identity is clicked', async () => {
      const user = await goToStep2()

      await user.click(screen.getByText('sub-1'))
      await user.click(screen.getByRole('button', { name: 'Transfer identity' }))

      expect(mockMutate).toHaveBeenCalledTimes(1)
      const [body] = mockMutate.mock.calls[0] as unknown[]
      expect(body).toEqual(
        expect.objectContaining({
          params: { path: { user_id: 'target-user' } },
          body: { identity_id: 'id-1' },
        })
      )
    })
  })

  describe('Navigation', () => {
    it('navigates back to identities tab when Cancel is clicked', async () => {
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })

      await user.click(screen.getByRole('link', { name: 'Cancel' }))

      expect(screen.getByRole('link', { name: 'Cancel' })).toHaveAttribute(
        'href',
        '/system-administration/access-management/users/target-user/identities'
      )
    })

    it('navigates to user detail when username link is clicked', async () => {
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })

      const aliceLink = screen.getByRole('link', { name: 'alice' })
      expect(aliceLink).toHaveAttribute('href', '/system-administration/access-management/users/user-1')
      await user.click(aliceLink)
    })

    it('navigates to identity provider detail when provider link is clicked', async () => {
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })

      await user.click(screen.getByText('bob@example.com'))
      await user.click(screen.getByRole('button', { name: 'Next' }))

      const azureLink = screen.getByRole('link', { name: 'Azure' })
      expect(azureLink).toHaveAttribute('href', '/system-administration/authentication/identity-providers/p-1')
      await user.click(azureLink)
    })
  })

  describe('Mutation callbacks', () => {
    it('shows success alert and navigates back on successful attach', async () => {
      const user = userEvent.setup()

      render(<TransferIdentityWizard />, { wrapper })

      await user.click(screen.getByText('bob@example.com'))
      await user.click(screen.getByRole('button', { name: 'Next' }))
      await user.click(screen.getByText('sub-1'))
      await user.click(screen.getByRole('button', { name: 'Transfer identity' }))

      const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
      act(() => {
        callbacks.onSuccess()
      })

      await waitFor(() => {
        expect(routerTestState.navigate).toHaveBeenCalledWith({
          to: '/system-administration/access-management/users/target-user/identities',
        })
      })
    })

    it('shows error alert on transfer failure', async () => {
      const user = userEvent.setup()
      render(<TransferIdentityWizard />, { wrapper })

      await user.click(screen.getByText('bob@example.com'))
      await user.click(screen.getByRole('button', { name: 'Next' }))
      await user.click(screen.getByText('sub-1'))
      await user.click(screen.getByRole('button', { name: 'Transfer identity' }))

      const callbacks = mockMutate.mock.calls[0][1] as { onError: (error: unknown) => void }
      act(() => {
        callbacks.onError(new Error('test error'))
      })

      await waitFor(() => {
        expect(screen.getByText('Failed to transfer identity')).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations on step 1', async () => {
      const { container } = render(<TransferIdentityWizard />, { wrapper })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations on step 2', async () => {
      const user = userEvent.setup()
      const { container } = render(<TransferIdentityWizard />, { wrapper })

      await user.click(screen.getByText('bob@example.com'))
      await user.click(screen.getByRole('button', { name: 'Next' }))

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
