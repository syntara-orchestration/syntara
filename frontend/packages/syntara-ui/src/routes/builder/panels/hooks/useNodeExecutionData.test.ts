import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useNodeExecutionData } from './useNodeExecutionData'

const mockUseQuery = vi.fn<(...args: unknown[]) => { data: unknown; isLoading: boolean }>()

vi.mock('../../../../client', () => ({
  executionsClient: {
    useQuery: (...args: unknown[]) => mockUseQuery(...args),
  },
}))

const mockUpstreamNodes = vi.fn<(...args: unknown[]) => { id: string; name: string; type: string }[]>()

vi.mock('./useUpstreamNodes', () => ({
  useUpstreamNodes: (...args: unknown[]) => mockUpstreamNodes(...args) as { id: string; name: string; type: string }[],
}))

describe('useNodeExecutionData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUpstreamNodes.mockReturnValue([])
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: false })
  })

  it('returns null data when no executionId is provided', () => {
    const { result } = renderHook(() => useNodeExecutionData('node-1'))

    expect(result.current).toEqual({
      inputData: null,
      outputData: null,
      isLoading: false,
    })
  })

  it('returns null data when executionId is null', () => {
    const { result } = renderHook(() => useNodeExecutionData('node-1', null))

    expect(result.current).toEqual({
      inputData: null,
      outputData: null,
      isLoading: false,
    })
  })

  it('passes enabled=false to useQuery when no executionId', () => {
    renderHook(() => useNodeExecutionData('node-1', null))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/activities',
      { params: { path: { execution_id: '' } } },
      { enabled: false }
    )
  })

  it('passes enabled=true to useQuery when executionId is provided', () => {
    renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/activities',
      { params: { path: { execution_id: 'exec-42' } } },
      { enabled: true }
    )
  })

  it('returns isLoading=true when query is loading', () => {
    mockUseQuery.mockReturnValue({ data: undefined, isLoading: true })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.isLoading).toBe(true)
    expect(result.current.inputData).toBeNull()
    expect(result.current.outputData).toBeNull()
  })

  it('returns outputData for current node when execution data exists', () => {
    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          {
            activity_name: 'node-1',
            output_data: { result: 'hello', count: 42 },
            status: 'completed',
          },
        ],
      },
      isLoading: false,
    })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.outputData).toEqual({ result: 'hello', count: 42 })
  })

  it('returns null outputData when activities do not contain the node', () => {
    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          {
            activity_name: 'other-node',
            output_data: { result: 'other' },
            status: 'completed',
          },
        ],
      },
      isLoading: false,
    })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.outputData).toBeNull()
  })

  it('returns inputData keyed by upstream node IDs', () => {
    mockUpstreamNodes.mockReturnValue([
      { id: 'upstream-a', name: 'Script A', type: 'script' },
      { id: 'upstream-b', name: 'Script B', type: 'script' },
    ])

    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          {
            activity_name: 'upstream-a',
            output_data: { value: 'from-a' },
            status: 'completed',
          },
          {
            activity_name: 'upstream-b',
            output_data: { value: 'from-b' },
            status: 'completed',
          },
          {
            activity_name: 'node-1',
            output_data: { result: 'output' },
            status: 'completed',
          },
        ],
      },
      isLoading: false,
    })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.inputData).toEqual({
      'upstream-a': { value: 'from-a' },
      'upstream-b': { value: 'from-b' },
    })
    expect(result.current.outputData).toEqual({ result: 'output' })
  })

  it('returns null inputData when upstream nodes have no output_data', () => {
    mockUpstreamNodes.mockReturnValue([{ id: 'upstream-a', name: 'Script A', type: 'script' }])

    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          {
            activity_name: 'upstream-a',
            output_data: null,
            status: 'running',
          },
        ],
      },
      isLoading: false,
    })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.inputData).toBeNull()
  })

  it('returns null inputData when no upstream nodes exist', () => {
    mockUpstreamNodes.mockReturnValue([])

    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          {
            activity_name: 'node-1',
            output_data: { result: 'output' },
            status: 'completed',
          },
        ],
      },
      isLoading: false,
    })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.inputData).toBeNull()
    expect(result.current.outputData).toEqual({ result: 'output' })
  })

  it('only includes upstream nodes that have matching activities', () => {
    mockUpstreamNodes.mockReturnValue([
      { id: 'upstream-a', name: 'Script A', type: 'script' },
      { id: 'upstream-missing', name: 'Missing', type: 'script' },
    ])

    mockUseQuery.mockReturnValue({
      data: {
        resources: [
          {
            activity_name: 'upstream-a',
            output_data: { value: 'from-a' },
            status: 'completed',
          },
        ],
      },
      isLoading: false,
    })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.inputData).toEqual({
      'upstream-a': { value: 'from-a' },
    })
  })

  it('handles empty resources array', () => {
    mockUseQuery.mockReturnValue({
      data: { resources: [] },
      isLoading: false,
    })

    const { result } = renderHook(() => useNodeExecutionData('node-1', 'exec-42'))

    expect(result.current.outputData).toBeNull()
    expect(result.current.inputData).toBeNull()
  })

  describe('workflowId fallback path', () => {
    it('fetches latest completed execution when workflowId is provided without executionId', () => {
      mockUpstreamNodes.mockReturnValue([{ id: 'upstream-1', name: 'Script', type: 'script' }])

      mockUseQuery.mockImplementation((_method: unknown, path: unknown) => {
        if (path === '/executions') {
          return {
            data: {
              resources: [{ id: 'latest-exec', status: 'completed', workflow_id: 'wf-1' }],
            },
            isLoading: false,
          }
        }
        if (path === '/executions/{execution_id}/activities') {
          return {
            data: {
              resources: [
                { activity_name: 'node-1', output_data: { result: 'done' }, status: 'completed' },
                { activity_name: 'upstream-1', output_data: { value: 'upstream-out' }, status: 'completed' },
              ],
            },
            isLoading: false,
          }
        }
        return { data: undefined, isLoading: false }
      })

      const { result } = renderHook(() => useNodeExecutionData('node-1', null, 'wf-1'))

      expect(result.current.outputData).toEqual({ result: 'done' })
      expect(result.current.inputData).toEqual({ 'upstream-1': { value: 'upstream-out' } })
    })

    it('returns null when latest execution is still running', () => {
      mockUseQuery.mockImplementation((_method: unknown, path: unknown) => {
        if (path === '/executions') {
          return {
            data: {
              resources: [{ id: 'running-exec', status: 'running', workflow_id: 'wf-1' }],
            },
            isLoading: false,
          }
        }
        return { data: undefined, isLoading: false }
      })

      const { result } = renderHook(() => useNodeExecutionData('node-1', null, 'wf-1'))

      expect(result.current.outputData).toBeNull()
      expect(result.current.inputData).toBeNull()
    })

    it('returns null when no executions exist for the workflow', () => {
      mockUseQuery.mockImplementation((_method: unknown, path: unknown) => {
        if (path === '/executions') {
          return { data: { resources: [] }, isLoading: false }
        }
        return { data: undefined, isLoading: false }
      })

      const { result } = renderHook(() => useNodeExecutionData('node-1', null, 'wf-1'))

      expect(result.current.outputData).toBeNull()
      expect(result.current.inputData).toBeNull()
    })
  })
})
