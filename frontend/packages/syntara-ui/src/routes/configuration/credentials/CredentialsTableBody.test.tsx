import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { Credential } from './credentialConstants'
import { GroupedCredentialsTableBody } from './CredentialsTableBody'

vi.mock('../../../components/table/LinkCell', () => ({
  LinkCell: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}))

vi.mock('./useCredentialPermissions', () => ({
  useCredentialPermissions: () => ({
    canCreate: true,
    canRead: true,
    canUpdate: true,
    canDelete: true,
    isLoading: false,
    tooltips: { create: '', read: '', update: '', enable: '', delete: '' },
  }),
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
})
