import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useCanI } from './useCanI'
import { useCrudResourcePermissions } from './useCrudResourcePermissions'

vi.mock('./useCanI', () => ({
  useCanI: vi.fn(),
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useCrudResourcePermissions', () => {
  beforeEach(() => {
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
  })

  it('returns tooltips for the resource type', () => {
    const { result } = renderHook(
      () =>
        useCrudResourcePermissions({
          resourceType: 'widget',
          tooltipTargets: { create: 'create a widget', update: 'edit this widget', delete: 'delete this widget' },
          createCheck: { options: undefined },
          updateCheck: { options: undefined },
          deleteCheck: { options: undefined },
        }),
      { wrapper: createWrapper() }
    )

    expect(result.current.canCreate).toBe(true)
    expect(result.current.tooltips.create).toContain('widget:create')
  })

  it('passes scoped options to useCanI', () => {
    renderHook(
      () =>
        useCrudResourcePermissions({
          resourceType: 'role',
          tooltipTargets: { create: 'create a role', update: 'edit this role', delete: 'delete this role' },
          createCheck: { options: { resourceProject: 'proj-1' } },
          updateCheck: { options: { resourceProject: 'proj-1' } },
          deleteCheck: { options: { resourceProject: 'proj-1' } },
        }),
      { wrapper: createWrapper() }
    )

    expect(useCanI).toHaveBeenCalledWith('create', 'role', { resourceProject: 'proj-1', enabled: true })
  })
})
