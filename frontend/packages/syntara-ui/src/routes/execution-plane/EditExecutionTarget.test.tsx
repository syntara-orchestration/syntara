import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useParams } from '@tanstack/react-router'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../app/AppRoute'
import { executionPlaneClient, integrationsClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import type { DirtyCheckOptions } from '../../providers/unsaved-changes/unsavedChangesContext'
import { expectPageTitle } from '../../test/pageTitle'

import { EditExecutionTarget } from './EditExecutionTarget'

const mockRegisterDirtyCheck: Mock<(opts: DirtyCheckOptions) => () => void> = vi.fn(() => () => {})
const mockNavigate = vi.fn()

function lastDirtyRegistration(): DirtyCheckOptions {
  const options = mockRegisterDirtyCheck.mock.calls.at(-1)?.[0]
  if (!options) {
    throw new Error('expected dirty-check registration')
  }
  return options
}

vi.mock('../../client', () => ({
  executionPlaneClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  integrationsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn(({ request }: { request: unknown }) => request) },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({
    registerDirtyCheck: mockRegisterDirtyCheck,
    requestNavigation: vi.fn(),
    registerSaveHandler: vi.fn(),
    unregisterSaveHandler: vi.fn(),
  }),
}))

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
      <a href={String(to)} {...rest}>
        {children}
      </a>
    ),
    useNavigate: () => mockNavigate,
    useParams: vi.fn(() => ({ executionTargetId: 'et-001' })),
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const state = { location: { pathname: '/execution-plane/et-001/edit', searchStr: '' } }
      return opts?.select ? opts.select(state) : state
    },
  }
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const OPENSHIFT_INTEGRATION = {
  id: 'b1000000-0000-4000-8000-000000000001',
  name: 'prod-openshift-east',
  integration_type: 'openshift',
}

const EXISTING_TARGET = {
  id: 'et-001',
  cluster_id: 'cl-001',
  name: 'Prod OpenShift West',
  backend_type: 'kubernetes',
  endpoint: 'https://api.west.example.com',
  placement: {
    type: 'kubernetes' as const,
    namespace: 'syntara-workers',
    node_selectors: ['workload=automation'],
  },
  status: 'active' as const,
  enabled: true,
  is_default: false,
  status_message: null,
  labels: { integration_id: 'integration-001' },
  created_at: '2026-01-01T00:00:00Z',
  last_ran_at: null,
}

function setupMocks(mutateOverrides?: Partial<{ mutate: ReturnType<typeof vi.fn>; isPending: boolean }>) {
  vi.mocked(executionPlaneClient.useQuery).mockReturnValue({
    data: EXISTING_TARGET,
    isPending: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  } as ReturnType<typeof executionPlaneClient.useQuery>)

  vi.mocked(integrationsClient.useQuery).mockReturnValue({
    data: { resources: [OPENSHIFT_INTEGRATION], next: null, prev: null, total: 1 },
    isPending: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  } as ReturnType<typeof integrationsClient.useQuery>)

  const mockMutate = vi.fn()
  vi.mocked(executionPlaneClient.useMutation).mockReturnValue({
    mutate: mockMutate,
    isPending: false,
    ...mutateOverrides,
  } as ReturnType<typeof executionPlaneClient.useMutation>)

  return { mockMutate }
}

describe('EditExecutionTarget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    mockNavigate.mockClear()
    mockRegisterDirtyCheck.mockClear()
    vi.mocked(useParams).mockReturnValue({ executionTargetId: 'et-001' })
    setupMocks()
  })

  it('pre-populates fields from the loaded execution target', async () => {
    render(<EditExecutionTarget />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Edit execution target' })).toBeInTheDocument()
    expectPageTitle(['Edit execution target', 'Execution Plane'])
    expect(screen.getByRole('textbox', { name: 'Execution target name' })).toHaveValue('Prod OpenShift West')
    expect(screen.getByRole('textbox', { name: 'Execution namespace' })).toHaveValue('syntara-workers')
    expect(screen.getByRole('textbox', { name: 'Node selector key 1' })).toHaveValue('workload')
    expect(screen.getByRole('textbox', { name: 'Node selector value 1' })).toHaveValue('automation')
    expect(screen.getByText('prod-openshift-east')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save execution target' })).toBeDisabled()
  })

  it('PATCHes only the changed name for a partial update', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<EditExecutionTarget />, { wrapper })

    const nameInput = await screen.findByRole('textbox', { name: 'Execution target name' })
    await user.clear(nameInput)
    await user.type(nameInput, 'Renamed West Target')
    await user.click(screen.getByRole('button', { name: 'Save execution target' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    expect(mockMutate.mock.calls[0]?.[0]).toEqual({
      params: { path: { target_id: 'et-001' } },
      body: { name: 'Renamed West Target' },
    })

    await waitFor(() => {
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onSuccess: (updated: { id: string }) => void }
      callbacks.onSuccess({ id: 'et-001' })
    })

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({
        to: AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', 'et-001'),
      })
    })
  })

  it('maps a server-side validation error onto the corresponding field and stays on the form', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<EditExecutionTarget />, { wrapper })

    const nameInput = await screen.findByRole('textbox', { name: 'Execution target name' })
    await user.clear(nameInput)
    await user.type(nameInput, 'bad-name')
    await user.click(screen.getByRole('button', { name: 'Save execution target' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    await waitFor(() => {
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onError: (err: unknown) => void }
      callbacks.onError({
        detail: [{ loc: ['body', 'name'], msg: 'Name is already reserved', type: 'value_error' }],
      })
    })

    expect(await screen.findByText('Name is already reserved')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Execution target name' })).toHaveValue('bad-name')
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('surfaces a conflict without navigating away', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<EditExecutionTarget />, { wrapper })

    const nameInput = await screen.findByRole('textbox', { name: 'Execution target name' })
    await user.clear(nameInput)
    await user.type(nameInput, 'Concurrent Edit')
    await user.click(screen.getByRole('button', { name: 'Save execution target' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    await waitFor(() => {
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onError: (err: unknown) => void }
      callbacks.onError({
        title: 'Conflict',
        detail: 'Execution target was modified by another user. Reload and try again.',
        code: 'CONFLICT',
        status: 409,
      })
    })

    expect(await screen.findByText(/modified by another user/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Edit execution target' })).toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('ignores PATCH success after the form is discarded mid-save', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<EditExecutionTarget />, { wrapper })

    const nameInput = await screen.findByRole('textbox', { name: 'Execution target name' })
    await user.clear(nameInput)
    await user.type(nameInput, 'Should Not Stick')
    await user.click(screen.getByRole('button', { name: 'Save execution target' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    act(() => {
      lastDirtyRegistration().exitWithoutSaving?.()
    })

    act(() => {
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onSuccess: (updated: { id: string }) => void }
      callbacks.onSuccess({ id: 'et-001' })
    })

    expect(mockNavigate).not.toHaveBeenCalled()
    expect(screen.queryByText('Execution target updated')).not.toBeInTheDocument()
  })

  it('rejects clearing a required field client-side before submit', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<EditExecutionTarget />, { wrapper })

    const nameInput = await screen.findByRole('textbox', { name: 'Execution target name' })
    await user.clear(nameInput)
    await user.click(screen.getByRole('button', { name: 'Save execution target' }))

    expect(await screen.findByText(/execution target name is required/i)).toBeInTheDocument()
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('registers a dirty-form guard that becomes active after edits', async () => {
    const user = userEvent.setup()
    render(<EditExecutionTarget />, { wrapper })

    await screen.findByRole('textbox', { name: 'Execution target name' })
    expect(mockRegisterDirtyCheck).toHaveBeenCalled()
    const dirtyCheck = lastDirtyRegistration()
    expect(dirtyCheck.title).toBe('Discard unsaved changes?')
    expect(dirtyCheck.body).toMatch(/unsaved changes to this execution target/i)
    expect(dirtyCheck.check()).toBe(false)

    await user.type(screen.getByRole('textbox', { name: 'Execution target name' }), 'x')
    expect(dirtyCheck.check()).toBe(true)
  })

  it('navigates to the detail page when Cancel is clicked', async () => {
    const user = userEvent.setup()
    render(<EditExecutionTarget />, { wrapper })

    await user.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(mockNavigate).toHaveBeenCalledWith({
      to: AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', 'et-001'),
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<EditExecutionTarget />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Edit execution target' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
