import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { authClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'
import type { DocKey } from '../../../utils/docs/types'
import { accessClient } from '../../access/accessClient'
import { COMPLIANT_TEST_PASSWORD } from '../passwordComplexity.testFixtures'

import { UserForm } from './UserForm'

const useDocLinkMock = vi.fn((key: DocKey) => `https://docs.example/${key}`)

vi.mock('../../../utils/docs/useDocLink', () => ({
  useDocLink: (key: DocKey) => useDocLinkMock(key),
}))

vi.mock('../../../client', () => ({
  authClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
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

vi.mock('../../access/useAllGroups', () => ({
  useAllGroups: () => ({
    groups: [
      { id: 'g1', name: 'users' },
      { id: 'g2', name: 'admins' },
      { id: 'g3', name: 'auditors' },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

const mockUseParams = vi.fn(() => ({}))
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  // Import global setup's router mock
  const { routerTestState, MockLink } = await import('../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => mockUseParams(),
    useNavigate: () => routerTestState.navigate,
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const state = { location: { pathname: routerTestState.pathname, searchStr: routerTestState.searchStr } }
      return opts?.select ? opts.select(state) : state
    },
  }
})

const VALID_UUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

function setupCreateMocks(mutateOverrides?: Partial<ReturnType<typeof vi.fn>>) {
  vi.mocked(authClient.useQuery).mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
  } as never)
  vi.mocked(accessClient.useQuery).mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
  } as never)
  const mockMutate = vi.fn()
  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    ...mutateOverrides,
  } as never)
  return { mockMutate }
}

const mockUserData = {
  id: VALID_UUID,
  username: 'jdoe',
  email: 'jdoe@example.com',
  first_name: 'John',
  last_name: 'Doe',
  is_enabled: true,
}

function setupEditMocks(mutateOverrides?: Partial<ReturnType<typeof vi.fn>>) {
  mockUseParams.mockReturnValue({ userId: VALID_UUID })
  vi.mocked(authClient.useQuery).mockReturnValue({
    data: undefined,
    isPending: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
  } as never)
  vi.mocked(accessClient.useQuery).mockReturnValue({
    data: mockUserData,
    isPending: false,
    isError: false,
    error: null,
    isFetching: false,
    refetch: vi.fn(),
  } as never)
  const mockMutate = vi.fn()
  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    ...mutateOverrides,
  } as never)
  return { mockMutate }
}

describe('UserForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    mockUseParams.mockReturnValue({})
  })

  describe('create mode', () => {
    it('renders with "Create User" heading and "Create user" submit button', () => {
      setupCreateMocks()
      render(<UserForm mode="create" />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Create User' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument()
    })

    it('uses createUser documentation key', () => {
      setupCreateMocks()
      render(<UserForm mode="create" />, { wrapper })

      expect(useDocLinkMock).toHaveBeenCalledWith('createUser')
      expect(screen.getByRole('link', { name: /documentation/i })).toHaveAttribute(
        'href',
        'https://docs.example/createUser'
      )
    })

    it('renders a Cancel button that navigates back to users list', async () => {
      setupCreateMocks()
      const user = userEvent.setup()
      render(<UserForm mode="create" />, { wrapper })

      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      expect(cancelButton).toBeInTheDocument()

      await user.click(cancelButton)

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/access-management/users',
      })
    })

    it('calls createUser mutation with form data on submit', async () => {
      const { mockMutate } = setupCreateMocks()
      const user = userEvent.setup()
      render(<UserForm mode="create" />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Username' }), 'newuser')
      await user.type(screen.getByRole('textbox', { name: 'First Name' }), 'New')
      await user.type(screen.getByRole('textbox', { name: 'Last Name' }), 'User')
      await user.type(screen.getByRole('textbox', { name: 'Email' }), 'new@example.com')
      await user.type(screen.getByLabelText('Password'), COMPLIANT_TEST_PASSWORD)

      await user.click(screen.getByRole('button', { name: 'Create user' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({
        body: {
          username: 'newuser',
          email: 'new@example.com',
          first_name: 'New',
          last_name: 'User',
          password: COMPLIANT_TEST_PASSWORD,
          is_enabled: true,
          group_names: ['users'],
        },
      })
    })

    it('navigates back on successful create', async () => {
      const { mockMutate } = setupCreateMocks()
      const user = userEvent.setup()
      render(<UserForm mode="create" />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Username' }), 'newuser')
      await user.type(screen.getByRole('textbox', { name: 'First Name' }), 'New')
      await user.type(screen.getByRole('textbox', { name: 'Last Name' }), 'User')
      await user.type(screen.getByRole('textbox', { name: 'Email' }), 'new@example.com')
      await user.type(screen.getByLabelText('Password'), COMPLIANT_TEST_PASSWORD)

      await user.click(screen.getByRole('button', { name: 'Create user' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Trigger onSuccess inside waitFor so React state updates are wrapped in act()
      await waitFor(() => {
        const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
        callbacks.onSuccess()
      })

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/access-management/users',
      })
    })

    it('calls onError handler on create failure', async () => {
      const { mockMutate } = setupCreateMocks()
      const user = userEvent.setup()
      render(<UserForm mode="create" />, { wrapper })

      await user.type(screen.getByRole('textbox', { name: 'Username' }), 'newuser')
      await user.type(screen.getByRole('textbox', { name: 'First Name' }), 'New')
      await user.type(screen.getByRole('textbox', { name: 'Last Name' }), 'User')
      await user.type(screen.getByRole('textbox', { name: 'Email' }), 'new@example.com')
      await user.type(screen.getByLabelText('Password'), COMPLIANT_TEST_PASSWORD)

      await user.click(screen.getByRole('button', { name: 'Create user' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Trigger onError inside waitFor so React state updates are wrapped in act()
      await waitFor(() => {
        const callbacks = mockMutate.mock.calls[0][1] as { onError: (err: unknown) => void }
        callbacks.onError(new Error('Conflict'))
      })
    })

    it('disables submit button while saving', () => {
      vi.mocked(authClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: true,
      } as never)

      render(<UserForm mode="create" />, { wrapper })

      // When isPending is true, the button has type="submit" and is disabled
      const submitButton = screen.getByRole('button', { name: /Create/i })
      expect(submitButton).toBeDisabled()
    })

    it('renders groups field with "users" pre-selected', () => {
      setupCreateMocks()
      render(<UserForm mode="create" />, { wrapper })

      expect(screen.getByText('Groups')).toBeInTheDocument()
      expect(screen.getByText('users')).toBeInTheDocument()
    })

    it('sends default group_names in create mutation body', async () => {
      const { mockMutate } = setupCreateMocks()
      const user = userEvent.setup()
      render(<UserForm mode="create" />, { wrapper })

      // Fill required fields and submit — default group_names should be ["users"]
      await user.type(screen.getByRole('textbox', { name: 'Username' }), 'newuser')
      await user.type(screen.getByRole('textbox', { name: 'First Name' }), 'New')
      await user.type(screen.getByLabelText('Password'), COMPLIANT_TEST_PASSWORD)

      await user.click(screen.getByRole('button', { name: 'Create user' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
      expect(callArgs[0].body.group_names).toEqual(['users'])
    })

    it('has no accessibility violations', async () => {
      setupCreateMocks()
      const { container } = render(<UserForm mode="create" />, { wrapper })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('edit mode', () => {
    it('renders with "Edit User" heading and "Save" submit button', () => {
      setupEditMocks()
      render(<UserForm mode="edit" />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Edit User' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
    })

    it('uses users documentation key', () => {
      setupEditMocks()
      render(<UserForm mode="edit" />, { wrapper })

      expect(useDocLinkMock).toHaveBeenCalledWith('users')
      expect(screen.getByRole('link', { name: /documentation/i })).toHaveAttribute('href', 'https://docs.example/users')
    })

    it('does not render the groups field', () => {
      setupEditMocks()
      render(<UserForm mode="edit" />, { wrapper })

      expect(screen.queryByText('Groups')).not.toBeInTheDocument()
    })

    it('calls updateUser mutation with form data on submit', async () => {
      const { mockMutate } = setupEditMocks()
      const user = userEvent.setup()
      render(<UserForm mode="edit" />, { wrapper })

      // Change the email field
      const emailInput = screen.getByRole('textbox', { name: 'Email' })
      await user.clear(emailInput)
      await user.type(emailInput, 'updated@example.com')

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0]
      expect(callArgs[0]).toEqual({
        params: { path: { user_id: VALID_UUID } },
        body: {
          username: 'jdoe',
          first_name: 'John',
          last_name: 'Doe',
          email: 'updated@example.com',
        },
      })
    })

    it('includes password in update body when provided', async () => {
      const { mockMutate } = setupEditMocks()
      const user = userEvent.setup()
      render(<UserForm mode="edit" />, { wrapper })

      await user.type(screen.getByLabelText('Password'), COMPLIANT_TEST_PASSWORD)

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      const callArgs = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
      expect(callArgs[0].body).toHaveProperty('password', COMPLIANT_TEST_PASSWORD)
    })

    it('navigates back on successful update', async () => {
      const { mockMutate } = setupEditMocks()
      const user = userEvent.setup()
      render(<UserForm mode="edit" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Trigger onSuccess inside waitFor so React state updates are wrapped in act()
      await waitFor(() => {
        const callbacks = mockMutate.mock.calls[0][1] as { onSuccess: () => void }
        callbacks.onSuccess()
      })

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/access-management/users',
      })
    })

    it('calls onError handler on update failure', async () => {
      const { mockMutate } = setupEditMocks()
      const user = userEvent.setup()
      render(<UserForm mode="edit" />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled()
      })

      // Trigger onError inside waitFor so React state updates are wrapped in act()
      await waitFor(() => {
        const callbacks = mockMutate.mock.calls[0][1] as { onError: (err: unknown) => void }
        callbacks.onError(new Error('Server error'))
      })
    })

    it('shows "User not found" empty state with Back and Retry buttons on query error', () => {
      mockUseParams.mockReturnValue({ userId: VALID_UUID })
      vi.mocked(authClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: true,
        error: new Error('Not found'),
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      render(<UserForm mode="edit" />, { wrapper })

      expect(screen.getByText('User not found')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Back to users/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument()
    })

    it('navigates back when Back to users button is clicked in error state', async () => {
      const user = userEvent.setup()
      mockUseParams.mockReturnValue({ userId: VALID_UUID })
      vi.mocked(authClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: true,
        error: new Error('Not found'),
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      render(<UserForm mode="edit" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Back to users/ }))

      expect(routerTestState.navigate).toHaveBeenCalledWith({
        to: '/system-administration/access-management/users',
      })
    })

    it('calls refetch when Retry button is clicked in error state', async () => {
      const user = userEvent.setup()
      const mockRefetch = vi.fn().mockResolvedValue({})
      mockUseParams.mockReturnValue({ userId: VALID_UUID })
      vi.mocked(authClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: true,
        error: new Error('Not found'),
        isFetching: false,
        refetch: mockRefetch,
      } as never)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      render(<UserForm mode="edit" />, { wrapper })

      await user.click(screen.getByRole('button', { name: /Retry/ }))

      expect(mockRefetch).toHaveBeenCalled()
    })

    it('shows loading state when query is pending', () => {
      mockUseParams.mockReturnValue({ userId: VALID_UUID })
      vi.mocked(authClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: false,
        isError: false,
        error: null,
        isFetching: false,
        refetch: vi.fn(),
      } as never)
      vi.mocked(accessClient.useQuery).mockReturnValue({
        data: undefined,
        isPending: true,
        isError: false,
        error: null,
        isFetching: true,
        refetch: vi.fn(),
        status: 'pending',
        fetchStatus: 'fetching',
      } as never)
      vi.mocked(accessClient.useMutation).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as never)

      render(<UserForm mode="edit" />, { wrapper })

      expect(screen.getByRole('heading', { name: 'Edit User' })).toBeInTheDocument()
      expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
      // The form submit button should not be visible in loading state
      expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
    })
  })
})
