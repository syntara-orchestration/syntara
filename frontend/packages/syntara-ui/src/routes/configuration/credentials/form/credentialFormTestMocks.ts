import { vi } from 'vitest'

import { credentialsClient } from '../../../../client'

export type CredentialTypeFixture = {
  id: string
  name: string
  description: string
  inputs: Record<string, unknown>
  injectors: Record<string, unknown>
  managed: boolean
}

export type CredentialTypesQueryMock = {
  data: { resources: CredentialTypeFixture[] } | undefined
  error: Error | null
  isLoading: boolean
  isPending: boolean
  isError: boolean
  isFetching: boolean
  refetch: ReturnType<typeof vi.fn>
}

export type CredentialMutationMock = {
  mutate: ReturnType<typeof vi.fn>
  isPending: boolean
}

export function mockCredentialTypesQuery(
  resources: CredentialTypeFixture[],
  overrides: Partial<CredentialTypesQueryMock> = {}
): CredentialTypesQueryMock {
  return {
    data: { resources },
    error: null,
    isLoading: false,
    isPending: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
    ...overrides,
  }
}

export function mockCredentialTypesQueryLoading(resources: CredentialTypeFixture[]): CredentialTypesQueryMock {
  return mockCredentialTypesQuery(resources, {
    data: undefined,
    isLoading: true,
    isPending: true,
    isFetching: true,
  })
}

export function mockCredentialMutation(mutate: ReturnType<typeof vi.fn>): CredentialMutationMock {
  return {
    mutate,
    isPending: false,
  }
}

export function asCredentialMutationResult(
  mock: CredentialMutationMock
): ReturnType<typeof credentialsClient.useMutation> {
  return mock
}

export function installCredentialTypesQueryMock(getState: () => CredentialTypesQueryMock): void {
  vi.mocked(credentialsClient.useQuery).mockImplementation(() => getState())
}
