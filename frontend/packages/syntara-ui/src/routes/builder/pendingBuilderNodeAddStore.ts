import { create } from 'zustand'

export type BuilderNodeAddRequest = {
  nodeTypeId: string
  nodeSubtypeId: string | null
}

export type BuilderNodeAddApply = (request: BuilderNodeAddRequest) => boolean

type PendingBuilderNodeAddState = {
  pending: BuilderNodeAddRequest | null
  /** null when the builder is unmounted; false when mounted but read-only. */
  canAcceptStepAdd: boolean | null
  apply: BuilderNodeAddApply | null
  setCanAcceptStepAdd: (value: boolean | null) => void
  registerApply: (apply: BuilderNodeAddApply | null) => void
  queue: (request: BuilderNodeAddRequest) => void
  take: () => BuilderNodeAddRequest | null
  clear: () => void
  request: (request: BuilderNodeAddRequest) => 'applied' | 'queued' | 'rejected'
}

function flushPending(
  apply: BuilderNodeAddApply | null,
  pending: BuilderNodeAddRequest | null
): BuilderNodeAddRequest | null {
  if (!apply || !pending) return pending
  apply(pending)
  return null
}

/**
 * Cross-tree bridge from the command palette (AppShell) to BuilderContent.
 * The palette requests a step; a registered builder apply handler opens
 * OPEN_NODE_EDITOR_ADD, or the request is queued until the builder mounts.
 */
export const usePendingBuilderNodeAddStore = create<PendingBuilderNodeAddState>((set, get) => ({
  pending: null,
  canAcceptStepAdd: null,
  apply: null,
  setCanAcceptStepAdd: (canAcceptStepAdd) => set({ canAcceptStepAdd }),
  registerApply: (apply) => {
    const pending = flushPending(apply, get().pending)
    set({ apply, pending })
  },
  queue: (request) => set({ pending: request }),
  take: () => {
    const { pending } = get()
    set({ pending: null })
    return pending
  },
  clear: () => set({ pending: null, apply: null, canAcceptStepAdd: null }),
  request: (request) => {
    const { apply, canAcceptStepAdd } = get()
    if (apply) return apply(request) ? 'applied' : 'rejected'
    if (canAcceptStepAdd === false) return 'rejected'
    set({ pending: request })
    return 'queued'
  },
}))
