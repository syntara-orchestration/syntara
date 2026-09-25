import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useCommandPaletteItems } from './useCommandPaletteItems'

vi.mock('../../app/useFilteredNavigationItems', () => ({
  useFilteredNavigationItems: () => [{ label: 'Workflows', path: '/workflows' }],
}))

vi.mock('../../hooks/useCanI', () => ({
  useCanI: () => ({ allowed: true, isChecking: false, isError: false }),
}))

vi.mock('../../routes/access/useAllProjects', () => ({
  useAllProjects: () => ({
    projects: [{ id: 'p1', name: 'Platform', description: null }],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../../routes/workflows/useAllWorkflows', () => ({
  useAllWorkflows: () => ({
    workflows: [{ id: 'wf-1', name: 'Deploy app', description: null }],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../../routes/configuration/settings/useAllSettings', () => ({
  useAllSettings: () => ({
    settings: [
      {
        key: 'app.debug',
        name: 'Debug',
        description: 'Verbose logs',
        category: 'system',
        group: 'General',
      },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../../routes/builder/registry/NodeRegistry', () => ({
  NodeRegistry: {
    getAll: () => [
      {
        id: 'action',
        label: 'Action',
        description: 'Run a script',
        keywords: ['http'],
        subtypes: [],
      },
    ],
  },
}))

describe('useCommandPaletteItems', () => {
  it('merges pages, steps, projects, workflows, and settings', () => {
    const { result } = renderHook(() => useCommandPaletteItems(true))

    const titles = result.current.items.map((item) => item.title)
    expect(titles).toEqual(expect.arrayContaining(['Workflows', 'Action', 'Platform', 'Deploy app', 'Debug']))
    expect(result.current.items.find((item) => item.title === 'Deploy app')?.to).toBe('/workflow-builder/wf-1')
    expect(result.current.isLoading).toBe(false)
  })
})
