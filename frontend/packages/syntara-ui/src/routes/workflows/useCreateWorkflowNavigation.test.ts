import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { routerTestState } from '../../test/setup'
import type { ProjectRead } from '../access/types'

import { useCreateWorkflowNavigation } from './useCreateWorkflowNavigation'

const project = (overrides: Partial<ProjectRead> = {}): ProjectRead => ({
  id: 'proj-1',
  name: 'payments',
  is_builtin: false,
  ...overrides,
})

describe('useCreateWorkflowNavigation', () => {
  beforeEach(() => {
    routerTestState.navigate.mockClear()
  })

  it('pre-fills the project picker with the project in view', () => {
    const { result } = renderHook(() => useCreateWorkflowNavigation(project(), 'proj-1'))
    result.current()
    expect(routerTestState.navigate).toHaveBeenCalledWith({
      to: '/workflow-builder/new',
      search: { projectId: 'proj-1' },
    })
  })

  it('falls back to the stable project id while the project is outside the loaded list', () => {
    const { result } = renderHook(() => useCreateWorkflowNavigation(null, 'proj-2'))
    result.current()
    expect(routerTestState.navigate).toHaveBeenCalledWith({
      to: '/workflow-builder/new',
      search: { projectId: 'proj-2' },
    })
  })

  it('opens the picker empty for "All projects"', () => {
    const { result } = renderHook(() => useCreateWorkflowNavigation(null, undefined))
    result.current()
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflow-builder/new', search: {} })
  })

  it('does not pre-fill a built-in project, which cannot hold workflows', () => {
    const { result } = renderHook(() => useCreateWorkflowNavigation(project({ is_builtin: true }), 'proj-1'))
    result.current()
    expect(routerTestState.navigate).toHaveBeenCalledWith({ to: '/workflow-builder/new', search: {} })
  })
})
