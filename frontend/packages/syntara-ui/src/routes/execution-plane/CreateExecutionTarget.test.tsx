import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AppRoute } from '../../app/AppRoute'
import { executionPlaneClient, integrationsClient } from '../../client'
import { AlertProvider } from '../../providers/alerts'
import { expectPageTitle } from '../../test/pageTitle'
import { routerTestState } from '../../test/setup'

import { CreateExecutionTarget } from './CreateExecutionTarget'

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

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  const { routerTestState: state, MockLink } = await import('../../test/setup')
  return {
    ...actual,
    Link: MockLink,
    useNavigate: () => state.navigate,
    useRouterState: (opts?: { select?: (s: { location: { pathname: string; searchStr: string } }) => unknown }) => {
      const routerState = { location: { pathname: state.pathname, searchStr: state.searchStr } }
      return opts?.select ? opts.select(routerState) : routerState
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

function setupMocks(mutateOverrides?: Partial<{ mutate: ReturnType<typeof vi.fn>; isPending: boolean }>) {
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

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole('textbox', { name: 'Execution target name' }), 'corp-internal-target')
  await user.type(screen.getByRole('textbox', { name: 'Execution namespace' }), 'aao-execution')
}

describe('CreateExecutionTarget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
    routerTestState.navigate.mockClear()
    setupMocks()
  })

  it('renders the configure form with readonly OpenShift cluster name', async () => {
    render(<CreateExecutionTarget />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Configure execution target' })).toBeInTheDocument()
    expectPageTitle(['Configure execution target', 'Execution Plane'])
    expect(screen.getByRole('heading', { level: 2, name: 'General' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Node selector and routing labels' })).toBeInTheDocument()
    expect(screen.getByText('prod-openshift-east')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Execution target name' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Execution namespace' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Node selector key 1' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Node selector value 1' })).toBeInTheDocument()
  })

  it('queries OpenShift integrations for the readonly cluster field', () => {
    render(<CreateExecutionTarget />, { wrapper })

    const call = vi.mocked(integrationsClient.useQuery).mock.calls[0]
    expect(call?.[0]).toBe('get')
    expect(call?.[1]).toBe('/integrations')
    const queryParams = (call?.[2] as { params?: { query?: Record<string, unknown> } } | undefined)?.params?.query
    expect(queryParams).toMatchObject({
      integration_type: 'openshift',
      limit: 1,
      include_total: true,
    })
  })

  it('does not show a cluster name when more than one OpenShift integration exists', async () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: { resources: [OPENSHIFT_INTEGRATION], next: null, prev: null, total: 2 },
      isPending: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    } as ReturnType<typeof integrationsClient.useQuery>)

    render(<CreateExecutionTarget />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Configure execution target' })).toBeInTheDocument()
    expect(screen.queryByText('prod-openshift-east')).not.toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('does not submit when required fields are empty', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<CreateExecutionTarget />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Configure execution target' }))

    expect(await screen.findByText(/execution target name is required/i)).toBeInTheDocument()
    expect(screen.getByText(/execution namespace is required/i)).toBeInTheDocument()
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('shows a field error for an invalid namespace and does not submit', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<CreateExecutionTarget />, { wrapper })

    await user.type(screen.getByRole('textbox', { name: 'Execution target name' }), 'corp-internal-target')
    await user.type(screen.getByRole('textbox', { name: 'Execution namespace' }), 'Invalid_Namespace')
    await user.click(screen.getByRole('button', { name: 'Configure execution target' }))

    expect(await screen.findByText(/invalid namespace format/i)).toBeInTheDocument()
    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('POSTs ExecutionTargetCreate and navigates to the new detail page on success', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<CreateExecutionTarget />, { wrapper })

    await fillRequiredFields(user)
    await user.type(screen.getByRole('textbox', { name: 'Node selector key 1' }), 'region')
    await user.type(screen.getByRole('textbox', { name: 'Node selector value 1' }), 'us-east')
    await user.click(screen.getByRole('button', { name: 'Configure execution target' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    expect(mockMutate.mock.calls[0]?.[0]).toEqual({
      body: {
        name: 'corp-internal-target',
        placement: {
          type: 'kubernetes',
          namespace: 'aao-execution',
          node_selectors: ['region=us-east'],
        },
      },
    })

    await waitFor(() => {
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onSuccess: (created: { id: string }) => void }
      callbacks.onSuccess({ id: 'et-new-001' })
    })

    expect(routerTestState.navigate).toHaveBeenCalledWith({
      to: AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', 'et-new-001'),
    })
  })

  it('keeps form values when create fails', async () => {
    const { mockMutate } = setupMocks()
    const user = userEvent.setup()
    render(<CreateExecutionTarget />, { wrapper })

    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: 'Configure execution target' }))

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalled()
    })

    await waitFor(() => {
      const callbacks = mockMutate.mock.calls[0]?.[1] as { onError: (err: unknown) => void }
      callbacks.onError({
        title: 'Conflict',
        detail: 'Expected exactly one installed Execution Plane cluster',
        status: 409,
      })
    })

    expect(screen.getByRole('textbox', { name: 'Execution target name' })).toHaveValue('corp-internal-target')
    expect(screen.getByRole('textbox', { name: 'Execution namespace' })).toHaveValue('aao-execution')
    const navigatedToDetail = routerTestState.navigate.mock.calls.some((call) => {
      const arg = call[0]
      return (
        typeof arg === 'object' &&
        arg !== null &&
        'to' in arg &&
        typeof arg.to === 'string' &&
        /\/execution-plane\/[^/]+$/.test(arg.to) &&
        !arg.to.endsWith('/create')
      )
    })
    expect(navigatedToDetail).toBe(false)
  })

  it('renders Cancel as a link to the execution plane list', async () => {
    render(<CreateExecutionTarget />, { wrapper })

    expect(await screen.findByRole('link', { name: 'Cancel' })).toHaveAttribute('href', AppRoute.ExecutionPlane.Root)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<CreateExecutionTarget />, { wrapper })

    expect(await screen.findByRole('heading', { level: 1, name: 'Configure execution target' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
