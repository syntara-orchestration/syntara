import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { nodeKindsClient } from '../client'

import { NODE_KINDS_QUERY_PATH, useNodeKindsQuery } from './useNodeKindsQuery'

vi.mock('../client', () => ({
  nodeKindsClient: {
    useQuery: vi.fn(),
  },
}))

const mockUseQuery = vi.mocked(nodeKindsClient.useQuery)

function mockResponse(data: unknown, { isSuccess = true }: { isSuccess?: boolean } = {}) {
  mockUseQuery.mockReturnValue({ data, isSuccess })
}

const scriptKind = {
  kind: 'script',
  category: 'action' as const,
  can_write: false,
  blocked_by: {
    kind: 'script',
    label: 'Script',
    reason: 'explicit_deny',
    policy: 'no-scripts-in-payments',
    scope: 'project',
    project: 'payments',
  },
}

const apiKind = {
  kind: 'http_request',
  category: 'action' as const,
  can_write: true,
  blocked_by: null,
}

describe('useNodeKindsQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the step-type verdicts for the selected project', () => {
    mockResponse([apiKind])

    renderHook(() => useNodeKindsQuery('project-1'))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      NODE_KINDS_QUERY_PATH,
      { params: { query: { project_id: 'project-1' } } },
      { enabled: true }
    )
  })

  it('skips the request while no project is selected', () => {
    mockResponse(undefined)

    const { result } = renderHook(() => useNodeKindsQuery(null))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      NODE_KINDS_QUERY_PATH,
      { params: { query: { project_id: '' } } },
      { enabled: false }
    )
    expect(result.current.nodeKinds).toEqual([])
  })

  it('keys the node kinds by kind', () => {
    mockResponse([scriptKind, apiKind])

    const { result } = renderHook(() => useNodeKindsQuery('project-1'))

    expect(result.current.nodeKindByKind.get('script')).toEqual(scriptKind)
    expect(result.current.nodeKindByKind.get('http_request')).toEqual(apiKind)
    expect(result.current.nodeKindByKind.get('condition')).toBeUndefined()
  })

  it('is unavailable when the request fails, so the panel fails closed', () => {
    mockResponse(undefined, { isSuccess: false })

    const { result } = renderHook(() => useNodeKindsQuery('project-1'))

    expect(result.current.isUnavailable).toBe(true)
  })

  it('is unavailable when the endpoint returns nothing, so the panel fails closed', () => {
    mockResponse([])

    const { result } = renderHook(() => useNodeKindsQuery('project-1'))

    expect(result.current.isUnavailable).toBe(true)
  })

  it('is available when the endpoint returns verdicts', () => {
    mockResponse([apiKind])

    const { result } = renderHook(() => useNodeKindsQuery('project-1'))

    expect(result.current.isUnavailable).toBe(false)
  })
})
