import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { integrationsClient } from '../../client'

import { useExecutionTargetClusterName } from './useExecutionTargetClusterName'

vi.mock('../../client', () => ({
  integrationsClient: {
    useQuery: vi.fn(),
  },
}))

const OPENSHIFT_INTEGRATION = {
  id: 'b1000000-0000-4000-8000-000000000001',
  name: 'prod-openshift-east',
  integration_type: 'openshift',
}

describe('useExecutionTargetClusterName', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('queries OpenShift integrations with a single-result limit', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: { resources: [OPENSHIFT_INTEGRATION], next: null, prev: null, total: 1 },
      isPending: false,
    } as ReturnType<typeof integrationsClient.useQuery>)

    renderHook(() => useExecutionTargetClusterName())

    expect(integrationsClient.useQuery).toHaveBeenCalledWith(
      'get',
      '/integrations',
      expect.objectContaining({
        params: {
          query: {
            integration_type: 'openshift',
            limit: 1,
            include_total: true,
          },
        },
      })
    )
  })

  it('returns the cluster name when exactly one OpenShift integration exists', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: { resources: [OPENSHIFT_INTEGRATION], next: null, prev: null, total: 1 },
      isPending: false,
    } as ReturnType<typeof integrationsClient.useQuery>)

    const { result } = renderHook(() => useExecutionTargetClusterName())

    expect(result.current.clusterName).toBe('prod-openshift-east')
    expect(result.current.isClusterPending).toBe(false)
  })

  it('omits the cluster name when more than one OpenShift integration exists', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: { resources: [OPENSHIFT_INTEGRATION], next: null, prev: null, total: 2 },
      isPending: false,
    } as ReturnType<typeof integrationsClient.useQuery>)

    const { result } = renderHook(() => useExecutionTargetClusterName())

    expect(result.current.clusterName).toBeUndefined()
  })

  it('reports pending while the integrations query is loading', () => {
    vi.mocked(integrationsClient.useQuery).mockReturnValue({
      data: undefined,
      isPending: true,
    } as ReturnType<typeof integrationsClient.useQuery>)

    const { result } = renderHook(() => useExecutionTargetClusterName())

    expect(result.current.isClusterPending).toBe(true)
    expect(result.current.clusterName).toBeUndefined()
  })
})
