import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessClient } from '../../access/accessClient'
import type { ProjectRead } from '../../access/types'

import { useOnlyWorkflowProjectId } from './useOnlyWorkflowProjectId'

vi.mock('../../access/accessClient', () => ({
  accessClient: { useQuery: vi.fn() },
}))

function project(id: string, isBuiltin = false): ProjectRead {
  return {
    id,
    name: id,
    description: null,
    labels: {},
    is_default: false,
    is_builtin: isBuiltin,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }
}

function mockProjects(
  resources: ProjectRead[],
  { next = null, isSuccess = true }: { next?: string | null; isSuccess?: boolean } = {}
) {
  vi.mocked(accessClient.useQuery).mockReturnValue({
    data: isSuccess ? { resources, next, prev: null } : undefined,
    isSuccess,
  })
}

describe('useOnlyWorkflowProjectId', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns the only project that can hold workflows', () => {
    mockProjects([project('payments')])
    expect(renderHook(() => useOnlyWorkflowProjectId()).result.current).toBe('payments')
  })

  it('ignores built-in projects', () => {
    mockProjects([project('builtin', true), project('payments')])
    expect(renderHook(() => useOnlyWorkflowProjectId()).result.current).toBe('payments')
  })

  it('returns undefined when several projects can hold workflows', () => {
    mockProjects([project('payments'), project('billing')])
    expect(renderHook(() => useOnlyWorkflowProjectId()).result.current).toBeUndefined()
  })

  it('returns undefined when more pages exist', () => {
    mockProjects([project('payments')], { next: 'cursor-2' })
    expect(renderHook(() => useOnlyWorkflowProjectId()).result.current).toBeUndefined()
  })

  it('returns undefined while loading or on error', () => {
    mockProjects([], { isSuccess: false })
    expect(renderHook(() => useOnlyWorkflowProjectId()).result.current).toBeUndefined()
  })

  it('returns undefined when only built-in projects exist', () => {
    mockProjects([project('builtin', true)])
    expect(renderHook(() => useOnlyWorkflowProjectId()).result.current).toBeUndefined()
  })

  it("reads the project picker's unfiltered first page, sharing its cache entry", () => {
    mockProjects([project('payments')])
    renderHook(() => useOnlyWorkflowProjectId())
    expect(accessClient.useQuery).toHaveBeenCalledWith('get', '/projects', { params: { query: { limit: 20 } } })
  })
})
