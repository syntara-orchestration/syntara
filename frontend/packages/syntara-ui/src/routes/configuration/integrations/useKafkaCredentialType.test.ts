import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useKafkaCredentialType } from './useKafkaCredentialType'

const { listCredentials, queryCredentials } = vi.hoisted(() => ({
  listCredentials: vi.fn(),
  queryCredentials: vi.fn(),
}))

vi.mock('../../../client', () => ({ credentialsClient: { useQuery: queryCredentials } }))
vi.mock('../../builder/components/useAllCredentials', () => ({ useAllCredentials: listCredentials }))

const credentialId = 'cred-identity'
const projectId = 'project-1'
const identity = { id: credentialId, credential_type_id: 'type-identity' }
const responses = {
  '/credentials/{credential_id}': identity,
  '/credential_types': {
    resources: [
      { id: 'type-kafka', name: 'Kafka' },
      { id: 'type-identity', name: 'mTLS Client Identity' },
    ],
  },
}
const credentialPath = { params: { path: { credential_id: credentialId } } }

describe('useKafkaCredentialType', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listCredentials.mockReturnValue({ credentials: [], isLoading: false })
    queryCredentials.mockImplementation(
      (_method: string, path: keyof typeof responses, _params: unknown, { enabled }: { enabled: boolean }) => ({
        data: enabled ? responses[path] : undefined,
      })
    )
  })

  it.each([undefined, null])('disables every request when the credential ID is %s', (id) => {
    const { result } = renderHook(() => useKafkaCredentialType(id, projectId))

    expect(result.current).toBeUndefined()
    expect(listCredentials).toHaveBeenCalledWith({ projectId, enabled: false })
    expect(queryCredentials).toHaveBeenCalledWith('get', '/credentials/{credential_id}', expect.anything(), {
      enabled: false,
    })
    expect(queryCredentials).toHaveBeenCalledWith('get', '/credential_types', undefined, { enabled: false })
  })

  it('resolves the type name from a project credential without fetching its details', () => {
    listCredentials.mockReturnValue({ credentials: [identity], isLoading: false })

    const { result } = renderHook(() => useKafkaCredentialType(credentialId, projectId))

    expect(result.current).toBe('mTLS Client Identity')
    expect(listCredentials).toHaveBeenCalledWith({ projectId, enabled: true })
    expect(queryCredentials).toHaveBeenCalledWith('get', '/credential_types', undefined, { enabled: true })
    expect(queryCredentials).toHaveBeenCalledWith('get', '/credentials/{credential_id}', credentialPath, {
      enabled: false,
    })
  })

  it('fetches the selected credential by ID when the project list has no match', () => {
    const { result } = renderHook(() => useKafkaCredentialType(credentialId, projectId))

    expect(queryCredentials).toHaveBeenCalledWith('get', '/credentials/{credential_id}', credentialPath, {
      enabled: true,
    })
    expect(result.current).toBe('mTLS Client Identity')
  })

  it('waits for the project list before fetching the credential by ID', () => {
    listCredentials.mockReturnValue({ credentials: [], isLoading: true })

    const { result } = renderHook(() => useKafkaCredentialType(credentialId, projectId))

    expect(result.current).toBeUndefined()
    expect(queryCredentials).toHaveBeenCalledWith('get', '/credentials/{credential_id}', credentialPath, {
      enabled: false,
    })
  })
})
