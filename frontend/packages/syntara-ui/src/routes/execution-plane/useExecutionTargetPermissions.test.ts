import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCanI } from '../../hooks/useCanI'

import { useExecutionTargetPermissions } from './useExecutionTargetPermissions'

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: false, isChecking: false, isError: false })),
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

function createWrapper() {
  return function Wrapper({ children }: { children: ReactNode }) {
    return QueryClientProvider({ client: queryClient, children })
  }
}

describe('useExecutionTargetPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
  })

  it('defaults to denying create until allowed', () => {
    const { result } = renderHook(() => useExecutionTargetPermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.tooltips.create).toMatch(/configure an execution target/i)
  })

  it('allows create when can_i grants execution_target:create', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })

    const { result } = renderHook(() => useExecutionTargetPermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(true)
  })

  it('checks create on execution_target', () => {
    renderHook(() => useExecutionTargetPermissions(), { wrapper: createWrapper() })

    expect(useCanI).toHaveBeenCalledWith('create', 'execution_target')
  })
})
