import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCanI } from '../../hooks/useCanI'

import type { ExecutionActivity } from './retryInputOverrides'
import { useRetryInputOverrides } from './useRetryInputOverrides'

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

const options = {
  enabled: true,
  executionProjectId: 'project-1',
  workflowDefinition: {
    nodes: [{ id: 'step-a', name: 'Deploy step', parameters: { code: 'exit 1' } }],
  },
  activityNameMap: new Map([['step-a', 'Deploy step']]),
  activities: [{ activity_id: 'step-a', status: 'failed' }] as ExecutionActivity[],
}

describe('useRetryInputOverrides', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
  })

  it('checks workflow edit permission in the execution project', () => {
    renderHook(() => useRetryInputOverrides(options))

    expect(useCanI).toHaveBeenCalledWith('update', 'workflow', {
      resourceProject: 'project-1',
      enabled: true,
    })
  })

  it('tracks edits, saves only retry overrides, and resets editor state', () => {
    const { result } = renderHook(() => useRetryInputOverrides(options))

    act(() => result.current.setPointIds(['step-a']))
    expect(result.current.state.targets).toEqual([
      expect.objectContaining({ id: 'step-a', name: 'Deploy step', parameterNames: ['code'] }),
    ])

    act(() => result.current.state.onEdit('step-a', JSON.stringify({ code: 'exit 1' }, null, 2)))
    expect(result.current.hasUnsavedInputOverrides).toBe(true)
    expect(result.current.state.drafts['step-a']).toBe(JSON.stringify({ code: 'exit 1' }, null, 2))

    act(() => result.current.state.onDraftChange('step-a', '{"code":"echo retry"}', { code: 'echo retry' }, undefined))
    expect(result.current.state.drafts['step-a']).toBe('{"code":"echo retry"}')

    act(() => result.current.state.onSave('step-a', { code: 'echo retry' }))
    expect(result.current.savedOverrides).toEqual({ 'step-a': { code: 'echo retry' } })
    expect(result.current.hasUnsavedInputOverrides).toBe(false)
    expect(result.current.state.editingTargetIds.has('step-a')).toBe(false)

    act(() => result.current.state.onEdit('step-a'))
    act(() => result.current.reset())
    expect(result.current.pointIds).toEqual([])
    expect(result.current.savedOverrides).toEqual({})
    expect(result.current.hasUnsavedInputOverrides).toBe(false)
  })
})
