import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { usersClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'

import { CreateUser } from './CreateUser'

vi.mock('../../../client', () => ({
  authClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  usersClient: { useQuery: vi.fn(), useMutation: vi.fn() },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
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
    useParams: () => ({}),
  }
})

vi.mock('../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('../../../hooks/routing/navigate', () => ({
  navigate: vi.fn(),
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

describe('CreateUser', () => {
  it('renders the create user form', () => {
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    } as never)
    vi.mocked(usersClient.useMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as never)

    render(<CreateUser />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Create user' })).toBeInTheDocument()
  })
})
