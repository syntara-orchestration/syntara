import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'

import { ProjectPoliciesTab } from './ProjectPoliciesTab'

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/builtinFilterDefinitions', async () => {
  const actual = await vi.importActual<typeof import('../../access/builtinFilterDefinitions')>(
    '../../access/builtinFilterDefinitions'
  )
  return actual
})

vi.mock('./EditProjectPolicyDialog', () => ({
  EditProjectPolicyDialog: ({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) => (
    <div role="dialog" aria-label="Edit project policy">
      <button type="button" onClick={onClose}>
        Close edit
      </button>
      <button type="button" onClick={onSuccess}>
        Save edit
      </button>
    </div>
  ),
}))

vi.mock('../../../hooks/routing/useNavigate', () => ({ useNavigate: () => vi.fn() }))

let searchParams = new URLSearchParams()
const setSearchParams = vi.fn((updater: URLSearchParams | ((prev: URLSearchParams) => URLSearchParams)) => {
  searchParams = typeof updater === 'function' ? updater(searchParams) : updater
})

vi.mock('../../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [searchParams, setSearchParams] as const,
}))

vi.mock('../../../hooks/routing/useSearch', () => ({ useSearch: () => '' }))
vi.mock('../../../hooks/routing/useLocation', () => ({ useLocation: () => '/' }))

const mockDeleteMutate = vi.fn()

const mockMutationReturn = {
  mutate: mockDeleteMutate,
  isPending: false,
  isError: false,
  error: null,
  data: null,
  reset: vi.fn(),
  isIdle: true,
  isSuccess: false,
  failureCount: 0,
  failureReason: null,
  context: undefined,
  submittedAt: 0,
  variables: undefined,
  status: 'idle',
  isPaused: false,
} as never

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockPolicies = [
  { id: 'p1', name: 'read-policy', description: 'Read access', is_builtin: true, project_id: null },
  { id: 'p2', name: 'custom-policy', description: null, is_builtin: false, project_id: 'proj-1' },
]

describe('ProjectPoliciesTab', () => {
  const mockRefetch = vi.fn().mockResolvedValue({})

  function setupMocks(policies = mockPolicies) {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: policies, total: policies.length },
      isLoading: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    vi.mocked(accessClient.useMutation).mockReturnValue(mockMutationReturn)
  }

  beforeEach(() => {
    vi.clearAllMocks()
    searchParams = new URLSearchParams()
    mockRefetch.mockResolvedValue({})
    setupMocks()
  })

  it('has no accessibility violations with policies', async () => {
    const { container } = render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when empty', async () => {
    setupMocks([])
    const { container } = render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders table with policy data', () => {
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('grid', { name: 'Project policies' })).toBeInTheDocument()
    expect(screen.getByText('read-policy')).toBeInTheDocument()
    expect(screen.getByText('custom-policy')).toBeInTheDocument()
    expect(screen.getByText('Read access')).toBeInTheDocument()
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('shows Built-in label for built-in policies', () => {
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('Built-in')).toBeInTheDocument()
  })

  it('shows Custom label for custom policies', () => {
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('Custom')).toBeInTheDocument()
  })

  it('renders empty state when no policies exist', () => {
    setupMocks([])
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    expect(screen.getByText('No policies yet')).toBeInTheDocument()
  })

  it('renders error state when query fails', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error('Network error'),
      refetch: vi.fn(),
    } as never)

    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Error' })).toBeInTheDocument()
  })

  it('renders loading state while fetching', () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as never)

    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
  })

  it('shows policy name and acknowledgement in delete dialog', async () => {
    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
    await user.click(kebabButtons[0])

    const deleteItem = await screen.findByText('Delete policy')
    await user.click(deleteItem)

    await waitFor(() => {
      expect(screen.getByText('Delete policy?')).toBeInTheDocument()
    })

    // Verify the policy name renders in the dialog body (covers deleteDialog.item?.name branch)
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('custom-policy')).toBeInTheDocument()
    expect(within(dialog).getByText(/will be deleted/)).toBeInTheDocument()
    expect(
      within(dialog).getByRole('checkbox', { name: 'I understand this policy will be permanently deleted.' })
    ).toBeInTheDocument()
  })

  it('calls showSuccess on successful delete', async () => {
    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
    await user.click(kebabButtons[0])

    const deleteItem = await screen.findByText('Delete policy')
    await user.click(deleteItem)

    // Check the acknowledgement checkbox before clicking Delete
    await user.click(screen.getByRole('checkbox'))

    const confirmButton = await screen.findByRole('button', { name: 'Delete' })
    await user.click(confirmButton)

    await waitFor(() => {
      expect(mockDeleteMutate).toHaveBeenCalled()
    })

    const callbacks = mockDeleteMutate.mock.calls[0][1] as { onSuccess: () => void; onSettled: () => void }
    act(() => {
      callbacks.onSuccess()
      callbacks.onSettled()
    })

    expect(mockRefetch).toHaveBeenCalled()
  })

  it('does not show row actions for built-in policies', () => {
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    expect(screen.getAllByRole('button', { name: 'Kebab toggle' })).toHaveLength(1)
  })

  it('opens edit dialog when Edit policy is selected from row actions', async () => {
    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Kebab toggle' }))
    await user.click(screen.getByRole('menuitem', { name: /edit policy/i }))

    expect(screen.getByRole('dialog', { name: 'Edit project policy' })).toBeInTheDocument()
  })

  it('refetches policies when edit is saved', async () => {
    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Kebab toggle' }))
    await user.click(screen.getByRole('menuitem', { name: /edit policy/i }))
    await user.click(screen.getByRole('button', { name: 'Save edit' }))

    expect(mockRefetch).toHaveBeenCalled()
  })

  it('closes edit dialog without refetch when edit is cancelled', async () => {
    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Kebab toggle' }))
    await user.click(screen.getByRole('menuitem', { name: /edit policy/i }))
    await user.click(screen.getByRole('button', { name: 'Close edit' }))

    expect(screen.queryByRole('dialog', { name: 'Edit project policy' })).not.toBeInTheDocument()
    expect(mockRefetch).not.toHaveBeenCalled()
  })

  it('shows filter empty state when filters are active but no results match', async () => {
    vi.mocked(accessClient.useQuery).mockImplementation((...args: unknown[]) => {
      const opts = args[2] as { params?: { query?: Record<string, unknown> } } | undefined
      const hasNameFilter = opts?.params?.query?.['name[contains]']
      return {
        data: hasNameFilter
          ? { resources: [], total: 0, next: null }
          : { resources: mockPolicies, total: mockPolicies.length, next: null },
        isPending: false,
        isError: false,
        error: null,
        refetch: mockRefetch,
      } as never
    })

    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    const nameFilter = screen.getByRole('textbox', { name: /name filter/i })
    await user.type(nameFilter, 'nonexistent')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('No results found')).toBeInTheDocument()
    })
  })

  it('loads the next page when pagination next is clicked', async () => {
    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: {
        resources: mockPolicies,
        total: mockPolicies.length,
        next: 'cursor-page-2',
      },
      isPending: false,
      isError: false,
      error: null,
      refetch: mockRefetch,
    } as never)

    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Go to next page' }))

    await waitFor(() => {
      expect(accessClient.useQuery).toHaveBeenCalled()
    })
  })

  it('calls showError on failed delete', async () => {
    const user = userEvent.setup()
    render(<ProjectPoliciesTab projectId="proj-1" />, { wrapper })

    const kebabButtons = screen.getAllByRole('button', { name: 'Kebab toggle' })
    await user.click(kebabButtons[0])

    const deleteItem = await screen.findByText('Delete policy')
    await user.click(deleteItem)

    // Check the acknowledgement checkbox before clicking Delete
    await user.click(screen.getByRole('checkbox'))

    const confirmButton = await screen.findByRole('button', { name: 'Delete' })
    await user.click(confirmButton)

    await waitFor(() => {
      expect(mockDeleteMutate).toHaveBeenCalled()
    })

    const callbacks = mockDeleteMutate.mock.calls[0][1] as { onError: (error: unknown) => void; onSettled: () => void }
    act(() => {
      callbacks.onError(new Error('Server error'))
      callbacks.onSettled()
    })

    expect(mockRefetch).not.toHaveBeenCalled()
  })
})
