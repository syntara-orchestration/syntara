import { NODE_KIND_BY_REGISTRY_ID, type NodeKind } from '@syntara/contracts'

import { type RegistryNodeIdUnion } from '../../../constants'

/**
 * Builder registry node id → backend node kind, typed for palette-entry
 * lookups. Data lives in `@syntara/contracts` (`NODE_KIND_BY_REGISTRY_ID`)
 * so both the UI and the mock API can consume it.
 */
export const nodeKindByRegistryId: Readonly<Partial<Record<RegistryNodeIdUnion, NodeKind>>> = NODE_KIND_BY_REGISTRY_ID

/**
 * Resolve the backend node kind a builder palette entry creates.
 *
 * Container entries (`trigger`, `action`, `logic`, `aap-execution`) only open
 * a subtype list, and the programmatic-only `generic` entry has no backend
 * node kind — all resolve to `null`.
 *
 * Once `GET /node_kinds` reports the kinds the backend actually serves, this
 * gains a `knownKinds` check so newly registered backend kinds resolve
 * without a mapping edit.
 *
 * @param registryNodeId Registry id of the palette entry (or subtype)
 * @returns The node kind, or `null` for container entries and unknown ids
 */
export function resolveNodeKind(registryNodeId: string): NodeKind | null {
  return NODE_KIND_BY_REGISTRY_ID[registryNodeId] ?? null
}
