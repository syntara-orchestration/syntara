import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { credentialsClient } from '../../../../client'
import { useSynForm } from '../../../../hooks/useSynForm'
import { AlertProvider } from '../../../../providers/alerts'
import { useSelectableProjects } from '../../../access/useAllProjects'
import type { Credential } from '../credentialConstants'

import { credentialFormSchema } from './credentialFormSchema'
import {
  asCredentialMutationResult,
  type CredentialTypeFixture,
  type CredentialTypesQueryMock,
  installCredentialTypesQueryMock,
  mockCredentialTypesQuery,
  mockCredentialTypesQueryLoading,
} from './credentialFormTestMocks'
import { useCredentialFormModal } from './useCredentialFormModal'

vi.mock('../../../../client', () => ({
  credentialsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

vi.mock('../../../access/useAllProjects', () => ({
  useSelectableProjects: vi.fn(),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockTypes: CredentialTypeFixture[] = [
  {
    id: 'type-1',
    name: 'HTTP Bearer Token',
    description: 'Bearer token authentication for HTTP APIs',
    inputs: {
      fields: [{ id: 'token', label: 'Token', type: 'string', secret: true, help_text: 'Bearer token value' }],
      required: ['token'],
    },
    injectors: {},
    managed: true,
  },
  {
    id: 'type-aap',
    name: 'Ansible Automation Platform',
    description: 'AAP API access',
    inputs: {
      fields: [
        { id: 'username', label: 'Username', type: 'string', secret: false },
        { id: 'password', label: 'Password', type: 'string', secret: true },
        { id: 'oauth_token', label: 'OAuth Token', type: 'string', secret: true },
      ],
      required: [],
      mutually_exclusive: [['oauth_token'], ['username', 'password']],
      mutually_exclusive_labels: ['OAuth2 Token', 'Basic Auth'],
    },
    injectors: {},
    managed: true,
  },
]

let typesQueryState: CredentialTypesQueryMock

const mockCredential: Credential = {
  id: 'cred-1',
  name: 'api-token',
  description: null,
  credential_type_id: 'type-1',
  project_id: 'proj-1',
  inputs: { token: 'secret' },
  labels: {},
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-02T00:00:00Z',
}

type HookProps = {
  isOpen: boolean
  credentialToEdit: Credential | null
  isEditMode: boolean
}

function renderCredentialModalHook(options: Partial<HookProps> = {}) {
  const onClose = vi.fn()
  const initialProps: HookProps = {
    isOpen: options.isOpen ?? true,
    credentialToEdit: options.credentialToEdit ?? null,
    isEditMode: options.isEditMode ?? false,
  }
  return renderHook(
    (props: HookProps) => {
      const form = useSynForm({
        schema: credentialFormSchema,
        defaultValues: {
          name: '',
          description: '',
          project_id: '',
          credential_type_id: '',
          inputs: {},
        },
        onClose,
      })
      const modalState = useCredentialFormModal({
        form,
        isOpen: props.isOpen,
        credentialToEdit: props.credentialToEdit,
        isEditMode: props.isEditMode,
      })
      return { form, modalState }
    },
    { wrapper, initialProps }
  )
}

describe('useCredentialFormModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    typesQueryState = mockCredentialTypesQuery(mockTypes)
    installCredentialTypesQueryMock(() => typesQueryState)
    vi.mocked(useSelectableProjects).mockReturnValue({
      projects: [],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    vi.mocked(credentialsClient.useMutation).mockReturnValue(
      asCredentialMutationResult({ mutate: vi.fn(), isPending: false })
    )
  })

  it('resets edit form with empty inputs when credential inputs are missing', async () => {
    const credentialWithoutInputs = { ...mockCredential, inputs: undefined } as Credential

    const { result } = renderCredentialModalHook({
      isOpen: true,
      credentialToEdit: credentialWithoutInputs,
      isEditMode: true,
    })

    await waitFor(() => {
      expect(result.current.form.getValues('inputs')).toEqual({})
      expect(result.current.form.getValues('name')).toBe('api-token')
    })
  })

  it('resets create form defaults when opened without a credential', async () => {
    const { result } = renderCredentialModalHook({ isOpen: true, credentialToEdit: null, isEditMode: false })

    await waitFor(() => {
      expect(result.current.form.getValues()).toMatchObject({
        name: '',
        description: '',
        project_id: '',
        credential_type_id: 'type-1',
        inputs: {},
      })
    })
  })

  it('auto-selects the first credential type when types finish loading in create mode', async () => {
    typesQueryState = mockCredentialTypesQueryLoading(mockTypes)

    const { result, rerender } = renderCredentialModalHook({ isOpen: true, isEditMode: false })

    result.current.form.setValue('name', 'typed before types loaded')

    typesQueryState = mockCredentialTypesQuery(mockTypes)
    rerender({ isOpen: true, credentialToEdit: null, isEditMode: false })

    await waitFor(() => {
      expect(result.current.form.getValues('name')).toBe('typed before types loaded')
      expect(result.current.form.getValues('credential_type_id')).toBe('type-1')
    })
  })

  it('does not reset the name when the same credential id is refreshed with a new object reference', async () => {
    const initial = { ...mockCredential }
    const { result, rerender } = renderCredentialModalHook({
      isOpen: true,
      credentialToEdit: initial,
      isEditMode: true,
    })

    await waitFor(() => expect(result.current.form.getValues('name')).toBe('api-token'))
    result.current.form.setValue('name', 'edited locally')

    const refreshed = { ...mockCredential, name: 'from server' }
    rerender({ isOpen: true, credentialToEdit: refreshed, isEditMode: true })

    expect(result.current.form.getValues('name')).toBe('edited locally')
  })

  it('selects the auth method group when types finish loading in edit mode', async () => {
    const aapCredential: Credential = {
      ...mockCredential,
      id: 'cred-aap',
      name: 'My AAP',
      credential_type_id: 'type-aap',
      inputs: { username: 'admin', password: '$encrypted$' },
    }

    typesQueryState = mockCredentialTypesQueryLoading(mockTypes)

    const { result, rerender } = renderCredentialModalHook({
      isOpen: true,
      credentialToEdit: aapCredential,
      isEditMode: true,
    })

    typesQueryState = mockCredentialTypesQuery(mockTypes)
    rerender({ isOpen: true, credentialToEdit: aapCredential, isEditMode: true })

    await waitFor(() => {
      expect(result.current.form.getValues('credential_type_id')).toBe('type-aap')
      expect(result.current.modalState.activeGroupIndex).toBe(1)
      expect(result.current.modalState.visibleFields.map((field) => field.id)).toEqual(['username', 'password'])
    })
  })
})
