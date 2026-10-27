import { NODE_KIND_BY_REGISTRY_ID } from '@syntara/contracts'

/** Resolve a concrete palette entry; containers and unknown ids have no kind. */
export function resolveNodeKind(registryStepId: string) {
  return Object.hasOwn(NODE_KIND_BY_REGISTRY_ID, registryStepId)
    ? NODE_KIND_BY_REGISTRY_ID[registryStepId as keyof typeof NODE_KIND_BY_REGISTRY_ID]
    : null
}
