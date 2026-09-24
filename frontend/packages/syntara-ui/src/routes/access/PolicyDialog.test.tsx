import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { AlertProvider } from '../../providers/alerts'

import { accessClient } from './accessClient'
import { PolicyDialog } from './PolicyDialog'
import type { PolicyRead } from './types'

vi.mock('./accessClient', () => ({ accessClient: { useMutation: vi.fn() } }))
vi.mock('./useAllProjects', () => ({
  useSelectableProjects: () => ({ projects: [{ id: 'proj-1', name: 'Project One' }], isLoading: false }),
}))

const { mockNodeKinds } = vi.hoisted(() => ({ mockNodeKinds: { current: [] as unknown[] } }))
vi.mock('../../hooks/useNodeKindsQuery', () => ({
  useNodeKindsQuery: () => ({
    query: { isPending: false },
    nodeKinds: mockNodeKinds.current,
    nodeKindByKind: new Map(),
    disabledKinds: new Set<string>(),
  }),
}))

const mockCreate = vi.fn()
const mockUpdate = vi.fn()
const mutationResult = (mutate: typeof mockCreate) => ({ mutate, isPending: false }) as never
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const policy: PolicyRead = {
  id: 'policy-1',
  name: 'custom-policy',
  description: 'Description',
  statements: [{ effect: 'allow', actions: ['workflow:read'], scope: 'project' }],
  scope: 'project',
  project_id: 'proj-1',
  is_builtin: false,
  is_project_eligible: true,
  is_system_scoped: false,
}

function renderDialog(editPolicy?: PolicyRead) {
  return render(
    <PolicyDialog
      policy={editPolicy}
      projectNameMap={new Map([['proj-1', 'Project One']])}
      onClose={vi.fn()}
      onSuccess={vi.fn()}
    />,
    { wrapper }
  )
}

async function enterValidPolicy(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole('textbox', { name: 'Policy name' }), 'new-policy')
  await user.clear(screen.getByRole('textbox', { name: 'Policy statements JSON' }))
  await user.click(screen.getByRole('textbox', { name: 'Policy statements JSON' }))
  await user.paste('[{"effect":"allow","actions":["workflow:read"],"scope":"any"}]')
}

describe('PolicyDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockNodeKinds.current = []
    vi.mocked(accessClient.useMutation).mockImplementation((_method, path) =>
      path === '/policies' ? mutationResult(mockCreate) : mutationResult(mockUpdate)
    )
  })

  it('creates a system policy with a null project id', async () => {
    const user = userEvent.setup()
    renderDialog()
    await enterValidPolicy(user)
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(mockCreate).toHaveBeenCalled())
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ body: { name: 'new-policy', project_id: null } })
  })

  it('creates a project policy with the selected project id', async () => {
    const user = userEvent.setup()
    renderDialog()
    await enterValidPolicy(user)
    await user.click(screen.getByRole('button', { name: 'Policy scope' }))
    await user.click(screen.getByRole('option', { name: 'Project' }))
    await user.click(screen.getByPlaceholderText('Select a project...'))
    await user.click(await screen.findByRole('option', { name: 'Project One' }))
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(mockCreate).toHaveBeenCalled())
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ body: { project_id: 'proj-1' } })
  })

  it('requires a project when project scope is selected', async () => {
    const user = userEvent.setup()
    renderDialog()
    await enterValidPolicy(user)
    await user.click(screen.getByRole('button', { name: 'Policy scope' }))
    await user.click(screen.getByRole('option', { name: 'Project' }))
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(mockCreate).not.toHaveBeenCalled())
  })

  it('updates a policy and shows its read-only scope', async () => {
    const user = userEvent.setup()
    renderDialog(policy)
    expect(screen.getByText('Scope: Project Project One')).toBeInTheDocument()
    await user.clear(screen.getByRole('textbox', { name: 'Policy name' }))
    await user.type(screen.getByRole('textbox', { name: 'Policy name' }), 'renamed-policy')
    await user.click(screen.getByRole('button', { name: 'Save policy' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalled())
    expect(mockUpdate.mock.calls[0][0]).toMatchObject({
      params: { path: { policy_id: 'policy-1' } },
      body: { name: 'renamed-policy', statements: policy.statements },
    })
  })

  it('submits a statement appended by the builder', async () => {
    mockNodeKinds.current = [
      {
        kind: 'script',
        category: 'action',
        enabled: true,
        switchable: true,
        deniable_actions: ['write'],
        can_write: true,
        attributes: [],
      },
    ]
    const user = userEvent.setup()
    renderDialog()
    await user.type(screen.getByRole('textbox', { name: 'Policy name' }), 'deny-script')
    await user.click(screen.getByRole('button', { name: 'Select a node kind' }))
    await user.click(await screen.findByRole('option', { name: 'script' }))
    await user.click(screen.getByRole('button', { name: 'Append to statements JSON' }))
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(mockCreate).toHaveBeenCalled())
    expect(mockCreate.mock.calls[0][0]).toMatchObject({
      body: { statements: [{ conditions: { resource_labels: { kind: 'script' } } }] },
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = renderDialog()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('explains that the statements JSON is the saved policy definition', () => {
    renderDialog()
    expect(screen.getByText(/The saved policy definition — a JSON array of statement objects/)).toBeInTheDocument()
  })

  it('reports success and closes after creation', async () => {
    const user = userEvent.setup()
    renderDialog()
    await enterValidPolicy(user)
    await user.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(mockCreate).toHaveBeenCalled())
    const callbacks = mockCreate.mock.calls[0][1] as { onSuccess: () => void }
    act(() => {
      callbacks.onSuccess()
    })
    expect(await screen.findByText('Policy created')).toBeInTheDocument()
  })
})
