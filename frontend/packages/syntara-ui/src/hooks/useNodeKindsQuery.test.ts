import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { nodeKindsClient } from '../client'

import { NODE_KINDS_QUERY_PATH, useNodeKindsQuery, useSetNodeKindEnabledMutation } from './useNodeKindsQuery'

vi.mock('../client', () => ({
  nodeKindsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
}))

const mockUseQuery = vi.mocked(nodeKindsClient.useQuery)
const mockUseMutation = vi.mocked(nodeKindsClient.useMutation)

type MockedQuery = { data: unknown; isPending: boolean }

function mockResponse(data: unknown) {
  mockUseQuery.mockReturnValue({ data, isPending: false })
}

const scriptKind = {
  kind: 'script',
  category: 'action' as const,
  enabled: true,
  switchable: true,
  deniable_actions: ['write', 'execute'],
  can_write: true,
}

const conditionKind = {
  kind: 'condition',
  category: 'flow_control' as const,
  enabled: true,
  switchable: false,
  deniable_actions: [],
  can_write: true,
}

describe('useNodeKindsQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the node-kind registry through the typed client', () => {
    mockResponse({ resources: [], disabled_kinds: [] })

    renderHook(() => useNodeKindsQuery())

    expect(mockUseQuery).toHaveBeenCalledWith('get', NODE_KINDS_QUERY_PATH, {}, { enabled: true })
  })

  it('passes enabled: false straight through so the request is skipped', () => {
    mockResponse(undefined)

    renderHook(() => useNodeKindsQuery({ enabled: false }))

    expect(mockUseQuery).toHaveBeenCalledWith('get', NODE_KINDS_QUERY_PATH, {}, { enabled: false })
  })

  it('exposes the resources list and a lookup map keyed by kind', () => {
    mockResponse({ resources: [scriptKind, conditionKind], disabled_kinds: [] })

    const { result } = renderHook(() => useNodeKindsQuery())

    expect(result.current.nodeKinds).toEqual([scriptKind, conditionKind])
    expect(result.current.nodeKindByKind.get('condition')).toEqual(conditionKind)
    expect(result.current.nodeKindByKind.has('mcp_tool')).toBe(false)
  })

  it('exposes the platform-wide disabled kinds as a set', () => {
    mockResponse({ resources: [scriptKind], disabled_kinds: ['agentic', 'mcp_tool'] })

    const { result } = renderHook(() => useNodeKindsQuery())

    expect(result.current.disabledKinds.has('agentic')).toBe(true)
    expect(result.current.disabledKinds.has('mcp_tool')).toBe(true)
    expect(result.current.disabledKinds.has('script')).toBe(false)
  })

  it('falls back to empty collections while the request is in flight', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isPending: true })

    const { result } = renderHook(() => useNodeKindsQuery())

    expect(result.current.nodeKinds).toEqual([])
    expect(result.current.nodeKindByKind.size).toBe(0)
    expect(result.current.disabledKinds.size).toBe(0)
    expect((result.current.query as unknown as MockedQuery).isPending).toBe(true)
  })

  it('keeps the derived map referentially stable across re-renders', () => {
    mockResponse({ resources: [scriptKind], disabled_kinds: [] })

    const { result, rerender } = renderHook(() => useNodeKindsQuery())
    const first = result.current.nodeKindByKind
    rerender()

    expect(result.current.nodeKindByKind).toBe(first)
  })
})

describe('useSetNodeKindEnabledMutation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('targets the kill-switch endpoint', () => {
    mockUseMutation.mockReturnValue({ mutate: vi.fn() })

    renderHook(() => useSetNodeKindEnabledMutation())

    expect(mockUseMutation).toHaveBeenCalledWith('put', '/node_kinds/{kind}/enabled')
  })
})
