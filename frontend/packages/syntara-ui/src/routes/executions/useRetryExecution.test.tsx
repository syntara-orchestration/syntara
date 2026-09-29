import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

import { executionsClient } from '../../client'

import { useRetryExecution } from './useRetryExecution'

const mockMutate = vi.fn()
const mockShowSuccess = vi.fn()
const mockShowError = vi.fn()

vi.mock('../../client', () => ({
  executionsClient: {
    useMutation: vi.fn(() => ({
      mutate: mockMutate,
      isPending: false,
    })),
  },
  authMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({
    showSuccess: mockShowSuccess,
    showError: mockShowError,
  }),
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

describe('useRetryExecution', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    })
  })

  it('calls mutate with the correct execution ID and shows success', () => {
    const mockOnSuccess = vi.fn()
    mockMutate.mockImplementation((_params: unknown, callbacks: { onSuccess: (data: { id: string }) => void }) => {
      callbacks.onSuccess({ id: 'new-exec-id' })
    })
    const { Wrapper, mockInvalidateQueries } = createWrapper()
    const { result } = renderHook(() => useRetryExecution('exec-abc', mockOnSuccess), { wrapper: Wrapper })

    act(() => {
      result.current.handleRetry()
    })

    expect(mockMutate).toHaveBeenCalledWith(
      { params: { path: { execution_id: 'exec-abc' } } },
      expect.objectContaining({
        onSuccess: expect.any(Function) as unknown,
        onError: expect.any(Function) as unknown,
      })
    )
    expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Execution retry started' })
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['get', '/executions/{execution_id}'] })
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['get', '/executions'] })
    expect(mockOnSuccess).toHaveBeenCalledWith('new-exec-id')
  })

  it('shows error alert on failure', () => {
    mockMutate.mockImplementation((_params: unknown, callbacks: { onError: (err: unknown) => void }) => {
      callbacks.onError({ detail: 'Execution not retryable' })
    })
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRetryExecution('exec-abc'), { wrapper: Wrapper })

    act(() => {
      result.current.handleRetry()
    })

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Failed to retry execution',
      description: 'Execution not retryable',
    })
  })

  it('returns isPending true when mutation is in progress', () => {
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
    })

    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRetryExecution('exec-abc'), { wrapper: Wrapper })

    expect(result.current.isPending).toBe(true)
  })

  it('returns isPending false when mutation is idle', () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useRetryExecution('exec-abc'), { wrapper: Wrapper })

    expect(result.current.isPending).toBe(false)
  })
})
