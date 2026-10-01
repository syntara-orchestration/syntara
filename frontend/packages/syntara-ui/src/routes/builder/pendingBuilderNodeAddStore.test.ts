import { describe, expect, it, vi } from 'vitest'

import { usePendingBuilderNodeAddStore } from './pendingBuilderNodeAddStore'

describe('usePendingBuilderNodeAddStore', () => {
  it('queues and takes a single pending add request', () => {
    usePendingBuilderNodeAddStore.getState().clear()
    usePendingBuilderNodeAddStore.getState().queue({ nodeTypeId: 'trigger', nodeSubtypeId: 'trigger-manual' })

    expect(usePendingBuilderNodeAddStore.getState().take()).toEqual({
      nodeTypeId: 'trigger',
      nodeSubtypeId: 'trigger-manual',
    })
    expect(usePendingBuilderNodeAddStore.getState().pending).toBeNull()
  })

  it('applies immediately when a builder handler is registered', () => {
    usePendingBuilderNodeAddStore.getState().clear()
    const apply = vi.fn(() => true)
    usePendingBuilderNodeAddStore.getState().registerApply(apply)

    expect(usePendingBuilderNodeAddStore.getState().request({ nodeTypeId: 'action', nodeSubtypeId: null })).toBe(
      'applied'
    )
    expect(apply).toHaveBeenCalled()
  })

  it('rejects when the open builder cannot accept a step', () => {
    usePendingBuilderNodeAddStore.getState().clear()
    usePendingBuilderNodeAddStore.getState().setCanAcceptStepAdd(false)

    expect(usePendingBuilderNodeAddStore.getState().request({ nodeTypeId: 'action', nodeSubtypeId: null })).toBe(
      'rejected'
    )
    expect(usePendingBuilderNodeAddStore.getState().pending).toBeNull()
  })
})
