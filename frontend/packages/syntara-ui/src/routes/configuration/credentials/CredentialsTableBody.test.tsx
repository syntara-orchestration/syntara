import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Credential } from './credentialConstants'
import { GroupedCredentialsTableBody } from './CredentialsTableBody'

vi.mock('../../../components/table/LinkCell', () => ({
  LinkCell: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}))

const { mockUseCredentialPermissions } = vi.hoisted(() => ({
  mockUseCredentialPermissions: vi.fn(),
}))

vi.mock('./useCredentialPermissions', () => ({
  useCredentialPermissions: mockUseCredentialPermissions,
}))

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const sampleCredential: Credential = {
  id: 'cred-1',
  name: 'GitHub Token',
  enabled: true,
  credential_type_id: 'type-1',
  project_id: 'proj-1',
} as Credential

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('GroupedCredentialsTableBody', () => {
  const onToggleEnabled = vi.fn()
  const onEdit = vi.fn()
  const onDelete = vi.fn()
  const getIsBuiltinProject = () => false

  beforeEach(() => {
    vi.clearAllMocks()
    mockUseCredentialPermissions.mockReturnValue({
      canCreate: true,
      canRead: true,
      canUpdate: true,
      canDelete: true,
      isLoading: false,
      isReadChecking: false,
      tooltips: { create: '', read: '', update: '', enable: '', delete: 'You need credential:delete' },
    })
  })

  it('renders project group header with credential rows', () => {
    const grouped = new Map([
      ['proj-1', { project: { id: 'proj-1', name: 'Project Alpha' } as never, credentials: [sampleCredential] }],
    ])

    render(
      <table>
        <GroupedCredentialsTableBody
          groupedCredentials={grouped}
          collapsedProjects={new Set()}
          onToggleProject={vi.fn()}
          typeMap={new Map([['type-1', { id: 'type-1', name: 'GitHub' } as never]])}
          expandedRows={new Set()}
          onToggleRow={vi.fn()}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleEnabled={onToggleEnabled}
          getIsBuiltinProject={getIsBuiltinProject}
        />
      </table>,
      { wrapper: createWrapper() }
    )

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.getByText('GitHub Token')).toBeInTheDocument()
  })

  it('renders "No project" header for unknown project id', () => {
    const grouped = new Map([['unknown', { project: null, credentials: [sampleCredential] }]])

    render(
      <table>
        <GroupedCredentialsTableBody
          groupedCredentials={grouped}
          collapsedProjects={new Set()}
          onToggleProject={vi.fn()}
          typeMap={new Map([['type-1', { id: 'type-1', name: 'GitHub' } as never]])}
          expandedRows={new Set()}
          onToggleRow={vi.fn()}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleEnabled={onToggleEnabled}
          getIsBuiltinProject={getIsBuiltinProject}
        />
      </table>,
      { wrapper: createWrapper() }
    )

    expect(screen.getByText('No project')).toBeInTheDocument()
    expect(screen.getByText('GitHub Token')).toBeInTheDocument()
  })

  it('hides credential rows when project group is collapsed', async () => {
    const user = userEvent.setup()
    const onToggleProject = vi.fn()
    const grouped = new Map([
      ['proj-1', { project: { id: 'proj-1', name: 'Project Alpha' } as never, credentials: [sampleCredential] }],
    ])

    render(
      <table>
        <GroupedCredentialsTableBody
          groupedCredentials={grouped}
          collapsedProjects={new Set(['proj-1'])}
          onToggleProject={onToggleProject}
          typeMap={new Map()}
          expandedRows={new Set()}
          onToggleRow={vi.fn()}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleEnabled={onToggleEnabled}
          getIsBuiltinProject={getIsBuiltinProject}
        />
      </table>,
      { wrapper: createWrapper() }
    )

    expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    expect(screen.queryByText('GitHub Token')).not.toBeInTheDocument()

    await user.click(screen.getByText('Project Alpha'))
    expect(onToggleProject).toHaveBeenCalledWith('proj-1')
  })

  it('passes each credential project_id to useCredentialPermissions', () => {
    const credA = { ...sampleCredential, id: 'cred-a', name: 'Cred A', project_id: 'proj-a' } as Credential
    const credB = { ...sampleCredential, id: 'cred-b', name: 'Cred B', project_id: 'proj-b' } as Credential

    const grouped = new Map([
      ['proj-a', { project: { id: 'proj-a', name: 'Project A' } as never, credentials: [credA] }],
      ['proj-b', { project: { id: 'proj-b', name: 'Project B' } as never, credentials: [credB] }],
    ])

    render(
      <table>
        <GroupedCredentialsTableBody
          groupedCredentials={grouped}
          collapsedProjects={new Set()}
          onToggleProject={vi.fn()}
          typeMap={new Map()}
          expandedRows={new Set()}
          onToggleRow={vi.fn()}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleEnabled={onToggleEnabled}
          getIsBuiltinProject={getIsBuiltinProject}
        />
      </table>,
      { wrapper: createWrapper() }
    )

    expect(mockUseCredentialPermissions).toHaveBeenCalledWith({ resourceProject: 'proj-a' })
    expect(mockUseCredentialPermissions).toHaveBeenCalledWith({ resourceProject: 'proj-b' })
  })

  it('disables enable toggle while per-row permissions are loading', async () => {
    mockUseCredentialPermissions.mockReturnValue({
      canCreate: false,
      canRead: false,
      canUpdate: false,
      canDelete: false,
      isLoading: true,
      isReadChecking: true,
      tooltips: { create: '', read: '', update: '', enable: '', delete: '' },
    })

    const user = userEvent.setup()
    const grouped = new Map([
      ['proj-1', { project: { id: 'proj-1', name: 'Project Alpha' } as never, credentials: [sampleCredential] }],
    ])

    render(
      <table>
        <GroupedCredentialsTableBody
          groupedCredentials={grouped}
          collapsedProjects={new Set()}
          onToggleProject={vi.fn()}
          typeMap={new Map()}
          expandedRows={new Set()}
          onToggleRow={vi.fn()}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleEnabled={onToggleEnabled}
          getIsBuiltinProject={getIsBuiltinProject}
        />
      </table>,
      { wrapper: createWrapper() }
    )

    const toggle = screen.getByRole('switch', { name: 'Enabled' })
    expect(toggle).toBeDisabled()

    await user.click(toggle)
    expect(onToggleEnabled).not.toHaveBeenCalled()
  })

  it('disables delete only for the row whose project is denied', async () => {
    const credAllowed = {
      ...sampleCredential,
      id: 'cred-ok',
      name: 'Allowed Cred',
      project_id: 'proj-ok',
    } as Credential
    const credDenied = { ...sampleCredential, id: 'cred-no', name: 'Denied Cred', project_id: 'proj-no' } as Credential

    mockUseCredentialPermissions.mockImplementation((opts?: { resourceProject?: string }) => {
      const denied = opts?.resourceProject === 'proj-no'
      return {
        canCreate: true,
        canRead: true,
        canUpdate: !denied,
        canDelete: !denied,
        isLoading: false,
        isReadChecking: false,
        tooltips: { create: '', read: '', update: 'no update', enable: 'no enable', delete: 'no delete' },
      }
    })

    const user = userEvent.setup()
    const grouped = new Map([
      ['proj-ok', { project: { id: 'proj-ok', name: 'Allowed' } as never, credentials: [credAllowed] }],
      ['proj-no', { project: { id: 'proj-no', name: 'Denied' } as never, credentials: [credDenied] }],
    ])

    render(
      <table>
        <GroupedCredentialsTableBody
          groupedCredentials={grouped}
          collapsedProjects={new Set()}
          onToggleProject={vi.fn()}
          typeMap={new Map()}
          expandedRows={new Set()}
          onToggleRow={vi.fn()}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleEnabled={onToggleEnabled}
          getIsBuiltinProject={getIsBuiltinProject}
        />
      </table>,
      { wrapper: createWrapper() }
    )

    // Open kebab for the allowed row
    const allowedKebab = screen.getByRole('button', { name: 'Actions for Allowed Cred' })
    await user.click(allowedKebab)
    const allowedDelete = await screen.findByRole('menuitem', { name: /Delete credential/ })
    expect(allowedDelete).not.toHaveAttribute('aria-disabled', 'true')
    // Close kebab
    await user.keyboard('{Escape}')

    // Open kebab for the denied row
    const deniedKebab = screen.getByRole('button', { name: 'Actions for Denied Cred' })
    await user.click(deniedKebab)
    const deniedDelete = await screen.findByRole('menuitem', { name: /Delete credential/ })
    expect(deniedDelete).toHaveAttribute('aria-disabled', 'true')
  })
})
