import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

import { executionsClient } from '../../../client'

import { useRetryFromFailure } from './useRetryFromFailure'

const mockMutate = vi.fn()
const mockShowSuccess = vi.fn()
const mockShowError = vi.fn()

vi.mock('../../../client', () => ({
  executionsClient: {
    useMutation: vi.fn(() => ({ mutate: mockMutate, isPending: false })),
  },
  authMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showSuccess: mockShowSuccess, showError: mockShowError }),
}))

function createWrapper() {
  const queryClient = new QueryClient()
  const mockInvalidateQueries = vi.fn().mockResolvedValue(undefined)
  vi.spyOn(queryClient, 'invalidateQueries').mockImplementation(mockInvalidateQueries)
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
  return { Wrapper, mockInvalidateQueries }
}

describe('useRetryFromFailure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('posts an empty body by default so the backend picks every failed node', () => {
    mockMutate.mockImplementation((_params: unknown, callbacks: { onSuccess: (data: { id: string }) => void }) => {
      callbacks.onSuccess({ id: 'new-exec-id' })
    })
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRetryFromFailure({ executionId: 'exec-abc' }), { wrapper: Wrapper })

    act(() => {
      result.current.handleRetry()
    })

    expect(mockMutate).toHaveBeenCalledWith(
      {
        params: { path: { execution_id: 'exec-abc' } },
        body: {},
      },
      expect.objectContaining({ onSuccess: expect.any(Function) as unknown, onError: expect.any(Function) as unknown })
    )
  })

  it('sends the selected retry points when a subset is chosen', () => {
    mockMutate.mockImplementation((_params: unknown, callbacks: { onSuccess: (data: { id: string }) => void }) => {
      callbacks.onSuccess({ id: 'new-exec-id' })
    })
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRetryFromFailure({ executionId: 'exec-abc' }), { wrapper: Wrapper })

    act(() => {
      result.current.handleRetry(['node-a'])
    })

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ body: { retry_point_ids: ['node-a'] } }),
      expect.anything()
    )
  })

  it('reports success and navigates to the new execution', () => {
    const mockOnSuccess = vi.fn()
    mockMutate.mockImplementation((_params: unknown, callbacks: { onSuccess: (data: { id: string }) => void }) => {
      callbacks.onSuccess({ id: 'new-exec-id' })
    })
    const { Wrapper, mockInvalidateQueries } = createWrapper()
    const { result } = renderHook(() => useRetryFromFailure({ executionId: 'exec-abc', onSuccess: mockOnSuccess }), {
      wrapper: Wrapper,
    })

    act(() => {
      result.current.handleRetry()
    })

    expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Retry started' })
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['get', '/executions/{execution_id}'] })
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['get', '/executions'] })
    expect(mockOnSuccess).toHaveBeenCalledWith('new-exec-id')
  })

  it('surfaces a rejection from the backend as an error alert', () => {
    mockMutate.mockImplementation((_params: unknown, callbacks: { onError: (err: unknown) => void }) => {
      callbacks.onError({ detail: 'Execution is still running.' })
    })
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRetryFromFailure({ executionId: 'exec-abc' }), { wrapper: Wrapper })

    act(() => {
      result.current.handleRetry()
    })

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Failed to retry from failure',
      description: 'Execution is still running.',
    })
  })

  it('reflects the pending state', () => {
    vi.mocked(executionsClient.useMutation).mockReturnValue({ mutate: mockMutate, isPending: true })
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRetryFromFailure({ executionId: 'exec-abc' }), { wrapper: Wrapper })

    expect(result.current.isPending).toBe(true)
  })
})