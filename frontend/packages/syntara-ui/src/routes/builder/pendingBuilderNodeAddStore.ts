import { create } from 'zustand'

export type BuilderNodeAddRequest = {
  nodeTypeId: string
  nodeSubtypeId: string | null
}

type PendingBuilderNodeAddState = {
  pending: BuilderNodeAddRequest | null
  queue: (request: BuilderNodeAddRequest) => void
  take: () => BuilderNodeAddRequest | null
  clear: () => void
}

/**
 * Cross-tree bridge from the command palette (AppShell) to BuilderContent.
 * The palette queues a step; the open builder consumes it as OPEN_NODE_EDITOR_ADD.
 */
export const usePendingBuilderNodeAddStore = create<PendingBuilderNodeAddState>((set, get) => ({
  pending: null,
  queue: (request) => set({ pending: request }),
  take: () => {
    const { pending } = get()
    set({ pending: null })
    return pending
  },
  clear: () => set({ pending: null }),
}))
