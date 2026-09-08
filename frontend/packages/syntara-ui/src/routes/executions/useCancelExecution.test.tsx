import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

import { executionsClient } from '../../client'

import { useCancelExecution } from './useCancelExecution'

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
  interfaceTagMiddleware: { onRequest: vi.fn() },
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

describe('useCancelExecution', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as never)
  })

  it('calls mutate with the correct execution ID and shows success', () => {
    mockMutate.mockImplementation((_params: unknown, callbacks: { onSuccess: () => void }) => {
      callbacks.onSuccess()
    })
    const { Wrapper, mockInvalidateQueries } = createWrapper()
    const { result } = renderHook(() => useCancelExecution('exec-abc'), { wrapper: Wrapper })

    act(() => {
      result.current.handleCancel()
    })

    expect(mockMutate).toHaveBeenCalledWith(
      { params: { path: { execution_id: 'exec-abc' } } },
      expect.objectContaining({
        onSuccess: expect.any(Function) as unknown,
        onError: expect.any(Function) as unknown,
      })
    )
    expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Run cancellation requested' })
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['get', '/executions/{execution_id}'] })
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['get', '/executions'] })
  })

  it('shows error alert on failure', () => {
    mockMutate.mockImplementation((_params: unknown, callbacks: { onError: (err: unknown) => void }) => {
      callbacks.onError({ detail: 'Cannot cancel completed execution' })
    })
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useCancelExecution('exec-abc'), { wrapper: Wrapper })

    act(() => {
      result.current.handleCancel()
    })

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Failure to cancel run',
      description: 'Cannot cancel completed execution',
    })
  })

  it('returns isPending true when mutation is in progress', () => {
    vi.mocked(executionsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
    } as never)

    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useCancelExecution('exec-abc'), { wrapper: Wrapper })

    expect(result.current.isPending).toBe(true)
  })

  it('returns isPending false when mutation is idle', () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useCancelExecution('exec-abc'), { wrapper: Wrapper })

    expect(result.current.isPending).toBe(false)
  })
})
