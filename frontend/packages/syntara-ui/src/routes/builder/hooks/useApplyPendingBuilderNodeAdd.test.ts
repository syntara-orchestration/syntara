import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { usePendingBuilderNodeAddStore } from '../pendingBuilderNodeAddStore'

import { useApplyPendingBuilderNodeAdd } from './useApplyPendingBuilderNodeAdd'

describe('useApplyPendingBuilderNodeAdd', () => {
  afterEach(() => {
    usePendingBuilderNodeAddStore.getState().clear()
  })
  it('opens the add-step editor when the builder can be edited', () => {
    const dispatch = vi.fn()
    usePendingBuilderNodeAddStore.getState().queue({ nodeTypeId: 'trigger', nodeSubtypeId: 'trigger-manual' })

    renderHook(() =>
      useApplyPendingBuilderNodeAdd(dispatch, { canEdit: true, isLoading: false, viewingVersion: null })
    )

    expect(dispatch).toHaveBeenCalledWith({
      type: 'OPEN_NODE_EDITOR_ADD',
      payload: { nodeTypeId: 'trigger', nodeSubtypeId: 'trigger-manual' },
    })
    expect(usePendingBuilderNodeAddStore.getState().pending).toBeNull()
  })

  it('waits while permissions are loading', () => {
    const dispatch = vi.fn()
    usePendingBuilderNodeAddStore.getState().queue({ nodeTypeId: 'action', nodeSubtypeId: null })

    const { rerender } = renderHook(
      (options: { canEdit: boolean; isLoading: boolean; viewingVersion: number | null }) =>
        useApplyPendingBuilderNodeAdd(dispatch, options),
      { initialProps: { canEdit: false, isLoading: true, viewingVersion: null } }
    )

    expect(dispatch).not.toHaveBeenCalled()
    expect(usePendingBuilderNodeAddStore.getState().pending).toEqual({
      nodeTypeId: 'action',
      nodeSubtypeId: null,
    })

    rerender({ canEdit: true, isLoading: false, viewingVersion: null })

    expect(dispatch).toHaveBeenCalledWith({
      type: 'OPEN_NODE_EDITOR_ADD',
      payload: { nodeTypeId: 'action', nodeSubtypeId: null },
    })
  })

  it('drops the request on a read-only or historical version view', () => {
    const dispatch = vi.fn()
    usePendingBuilderNodeAddStore.getState().queue({ nodeTypeId: 'action', nodeSubtypeId: null })

    renderHook(() =>
      useApplyPendingBuilderNodeAdd(dispatch, { canEdit: false, isLoading: false, viewingVersion: null })
    )

    expect(dispatch).not.toHaveBeenCalled()
    expect(usePendingBuilderNodeAddStore.getState().pending).toBeNull()
  })

  it('drops the request while viewing a historical version', () => {
    const dispatch = vi.fn()
    usePendingBuilderNodeAddStore.getState().queue({ nodeTypeId: 'action', nodeSubtypeId: null })

    renderHook(() => useApplyPendingBuilderNodeAdd(dispatch, { canEdit: true, isLoading: false, viewingVersion: 2 }))

    expect(dispatch).not.toHaveBeenCalled()
    expect(usePendingBuilderNodeAddStore.getState().pending).toBeNull()
  })
})
