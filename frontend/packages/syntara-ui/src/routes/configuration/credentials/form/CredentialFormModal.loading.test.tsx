import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { credentialsClient } from '../../../../client'
import { AlertProvider } from '../../../../providers/alerts'
import { useSelectableProjects } from '../../../access/useAllProjects'
import type { Credential } from '../credentialConstants'

import { CredentialFormModal } from './CredentialFormModal'
import { asCredentialMutationResult, mockCredentialTypesQuery } from './credentialFormTestMocks'

vi.mock('../../../../client', () => ({
  credentialsClient: { useQuery: vi.fn(), useMutation: vi.fn() },
}))
vi.mock('../../../access/useAllProjects', () => ({ useSelectableProjects: vi.fn() }))

const USERNAME = 'Username'
const SAVE = 'Save credential'
const RETRY = 'Retry'
const ERROR_TITLE = 'Unable to load credential'
const MASKED = '$encrypted$'
const credential: Credential = {
  id: 'kafka-credential',
  name: 'Kafka login',
  project_id: 'project-1',
  credential_type_id: 'kafka-type',
  inputs: { username: MASKED, password: MASKED },
}
const detail: Credential = { ...credential, inputs: { username: 'operator', password: MASKED } }
const typesQuery = mockCredentialTypesQuery([
  {
    id: 'kafka-type',
    name: 'Kafka',
    description: 'Kafka login',
    managed: true,
    injectors: {},
    inputs: {
      fields: [
        { id: 'username', label: USERNAME, type: 'string', secret: false },
        { id: 'password', label: 'Password', type: 'string', secret: true },
      ],
      required: ['username', 'password'],
    },
  },
])
let detailQuery: {
  data: Credential | undefined
  error: Error | null
  isError: boolean
  isPending: boolean
  isLoading: boolean
  isFetching: boolean
  refetch: ReturnType<typeof vi.fn>
}
const mutate = vi.fn()

function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <AlertProvider>{children}</AlertProvider>
    </QueryClientProvider>
  )
}

function modal(isOpen = true, selected = credential) {
  return <CredentialFormModal isOpen={isOpen} onClose={vi.fn()} credentialToEdit={{ ...selected }} />
}

describe('credential edit detail loading', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    detailQuery = {
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
      isLoading: true,
      isFetching: true,
      refetch: vi.fn(),
    }
    vi.mocked(credentialsClient.useQuery).mockImplementation((_method, path) =>
      path === '/credentials/{credential_id}' ? detailQuery : typesQuery
    )
    vi.mocked(credentialsClient.useMutation).mockReturnValue(asCredentialMutationResult({ mutate, isPending: false }))
    vi.mocked(useSelectableProjects).mockReturnValue({ projects: [], isLoading: false, error: null, refetch: vi.fn() })
  })

  it('prevents editing and saving until the delayed detail response arrives', async () => {
    const user = userEvent.setup()
    const { rerender } = render(modal(), { wrapper: Wrapper })

    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: USERNAME })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: SAVE })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: SAVE }))
    expect(mutate).not.toHaveBeenCalled()

    detailQuery = { ...detailQuery, data: detail, isPending: false, isLoading: false, isFetching: false }
    rerender(modal())
    expect(screen.getByRole('textbox', { name: USERNAME })).toHaveValue('operator')
    expect(screen.getByRole('button', { name: SAVE })).toBeEnabled()
  })

  it('shows a retryable detail error and opens the editor after retry succeeds', async () => {
    const user = userEvent.setup()
    detailQuery = {
      ...detailQuery,
      error: Object.assign(new Error('Network error'), { retryable: true }),
      isError: true,
      isPending: false,
      isLoading: false,
    }
    const { rerender } = render(modal(), { wrapper: Wrapper })

    expect(screen.getByRole('heading', { name: ERROR_TITLE })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: USERNAME })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: SAVE })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: RETRY }))
    expect(detailQuery.refetch).toHaveBeenCalledOnce()

    detailQuery = { ...detailQuery, data: detail, error: null, isError: false }
    rerender(modal())
    expect(screen.getByRole('textbox', { name: USERNAME })).toHaveValue('operator')
  })

  it('preserves unsaved inputs through successful and failed background refetches', async () => {
    const user = userEvent.setup()
    detailQuery = { ...detailQuery, data: detail, isPending: false, isLoading: false }
    const { rerender } = render(modal(), { wrapper: Wrapper })
    await user.clear(screen.getByRole('textbox', { name: USERNAME }))
    await user.type(screen.getByRole('textbox', { name: USERNAME }), 'my-draft')

    detailQuery = { ...detailQuery, data: { ...detail, inputs: { username: 'server-update', password: MASKED } } }
    rerender(modal())
    expect(screen.getByRole('textbox', { name: USERNAME })).toHaveValue('my-draft')

    detailQuery = { ...detailQuery, error: new Error('Network error'), isError: true }
    rerender(modal())
    expect(screen.getByRole('textbox', { name: USERNAME })).toHaveValue('my-draft')
    await user.click(screen.getByRole('button', { name: SAVE }))
    expect(mutate).toHaveBeenCalledOnce()
    expect(mutate.mock.calls[0]?.[0]).toHaveProperty('body.inputs', { username: 'my-draft', password: MASKED })
  })

  it('initializes from current detail when reopened or switched to another credential', async () => {
    const user = userEvent.setup()
    detailQuery = { ...detailQuery, data: detail, isPending: false, isLoading: false }
    const { rerender } = render(modal(), { wrapper: Wrapper })
    await user.type(screen.getByRole('textbox', { name: USERNAME }), '-draft')
    rerender(modal(false))
    detailQuery = { ...detailQuery, data: { ...detail, inputs: { username: 'reopened', password: MASKED } } }
    rerender(modal())
    expect(screen.getByRole('textbox', { name: USERNAME })).toHaveValue('reopened')

    const other = {
      ...detail,
      id: 'other-credential',
      name: 'Other login',
      inputs: { username: 'other', password: MASKED },
    }
    detailQuery = { ...detailQuery, data: other }
    rerender(modal(true, other))
    expect(screen.getByRole('textbox', { name: USERNAME })).toHaveValue('other')
  })

  it('keeps cancel available during loading', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<CredentialFormModal isOpen onClose={onClose} credentialToEdit={credential} />, { wrapper: Wrapper })
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('has no accessibility violations while loading or showing a detail error', async () => {
    const { container, rerender } = render(modal(), { wrapper: Wrapper })
    expect(await axe(container)).toHaveNoViolations()
    detailQuery = { ...detailQuery, error: new Error('Network error'), isError: true }
    rerender(modal())
    expect(await axe(container)).toHaveNoViolations()
  })
})
