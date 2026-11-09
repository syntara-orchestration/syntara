import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
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
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useExecutionTargetPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
  })

  it('defaults to denying create, update, and delete until allowed', () => {
    const { result } = renderHook(() => useExecutionTargetPermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(false)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(false)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.tooltips.create).toMatch(/configure an execution target/i)
    expect(result.current.tooltips.update).toMatch(/edit this execution target/i)
    expect(result.current.tooltips.update).toContain('execution_target:update')
    expect(result.current.tooltips.delete).toMatch(/delete this execution target/i)
    expect(result.current.tooltips.delete).toContain('execution_target:delete')
  })

  it('reports loading while any can_i check is in flight', () => {
    vi.mocked(useCanI).mockImplementation((action) => {
      if (action === 'update') {
        return { allowed: false, isChecking: true, isError: false }
      }
      return { allowed: true, isChecking: false, isError: false }
    })

    const { result } = renderHook(() => useExecutionTargetPermissions(), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(false)
    expect(result.current.canDelete).toBe(true)
  })

  it('allows create, update, and delete when can_i grants all', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })

    const { result } = renderHook(() => useExecutionTargetPermissions(), { wrapper: createWrapper() })

    expect(result.current.canCreate).toBe(true)
    expect(result.current.canUpdate).toBe(true)
    expect(result.current.canDelete).toBe(true)
  })

  it('checks create, update, and delete on execution_target', () => {
    renderHook(() => useExecutionTargetPermissions(), { wrapper: createWrapper() })

    expect(useCanI).toHaveBeenCalledWith('create', 'execution_target')
    expect(useCanI).toHaveBeenCalledWith('update', 'execution_target')
    expect(useCanI).toHaveBeenCalledWith('delete', 'execution_target')
  })
})
