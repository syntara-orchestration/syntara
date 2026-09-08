import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { authClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'

import { EditUser } from './EditUser'

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

vi.mock('../../../hooks/routing/useLocation', () => ({
  useLocation: () => '/',
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { MockLink } = await import('../../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useParams: () => ({ userId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890' }),
  }
})

vi.mock('../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('../../../hooks/routing/navigate', () => ({
  navigate: vi.fn(),
}))

const VALID_UUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockUserData = {
  id: VALID_UUID,
  username: 'jdoe',
  email: 'jdoe@example.com',
  first_name: 'John',
  last_name: 'Doe',
  is_enabled: true,
}

function setupSuccessMocks() {
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
  vi.mocked(accessClient.useMutation).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as never)
}

describe('EditUser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('renders the edit user form with heading and save button', () => {
    setupSuccessMocks()
    render(<EditUser />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Edit John Doe' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('does not render the status toggle on the edit form', () => {
    setupSuccessMocks()
    render(<EditUser />, { wrapper })

    expect(screen.queryByLabelText('Enabled')).not.toBeInTheDocument()
    expect(screen.queryByText('Status')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    setupSuccessMocks()
    const { container } = render(<EditUser />, { wrapper })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
