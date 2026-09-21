import { describe, expect, it } from 'vitest'

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
})
