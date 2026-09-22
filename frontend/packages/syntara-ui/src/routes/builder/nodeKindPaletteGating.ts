import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import { resolveNodeKind } from './registry/nodeKindMapping'

/** Minimal palette entry shape the gate needs — a registry node type or one of its subtypes. */
export type GateablePaletteEntry = {
  id: string
  subtypes?: readonly { id: string }[]
}

/** Gating verdict for one palette entry. */
export type PaletteEntryGate = {
  /** The backend node kind this entry creates, or `null` for container entries. */
  kind: string | null
  /** The kind is switched off platform-wide — the entry is dropped from the palette (F-13). */
  isHidden: boolean
  /** The caller may not introduce this kind — the entry stays visible but inert (F-7/F-8). */
  isDenied: boolean
}

/** Tooltip shown on a palette entry the caller may not add. */
export function nodeKindDeniedTooltip(kind: string): string {
  return `You are not allowed to add ${kind} nodes`
}

function gateForKind(entry: NodeKind | undefined): { isHidden: boolean; isDenied: boolean } {
  if (!entry) return { isHidden: false, isDenied: false }
  return { isHidden: !entry.enabled, isDenied: !entry.can_write }
}

/**
 * Decide, per palette entry, whether it must be hidden or shown disabled.
 *
 * Two independent rules meet here:
 *
 * - The kill switch (`enabled: false`) is platform-wide and not a permission, so
 *   the entry disappears from the palette entirely (F-13/F-14).
 * - A `workflow_node:write` deny (`can_write: false`) keeps the entry visible but
 *   inert with an explanatory tooltip (F-7/F-8). Nodes of that kind already on the
 *   canvas are untouched: write means *introducing* a kind, not editing it.
 *
 * Container entries (`trigger`, `action`, `logic`, `aap-execution`) create no node
 * themselves; they inherit the verdict of their subtypes and are only hidden or
 * disabled when every subtype is.
 *
 * @param entry Palette entry, optionally carrying its subtypes.
 * @param nodeKindByKind Registry entries from `GET /node_kinds`, keyed by kind.
 * @returns The gating verdict for the entry.
 */
export function gatePaletteEntry(
  entry: GateablePaletteEntry,
  nodeKindByKind: ReadonlyMap<string, NodeKind>
): PaletteEntryGate {
  const knownKinds = new Set(nodeKindByKind.keys())

  if (entry.subtypes?.length) {
    const subtypeGates = entry.subtypes.map((subtype) =>
      gateForKind(nodeKindByKind.get(resolveNodeKind(subtype.id, knownKinds) ?? ''))
    )
    return {
      kind: null,
      isHidden: subtypeGates.every((gate) => gate.isHidden),
      isDenied: subtypeGates.every((gate) => gate.isHidden || gate.isDenied),
    }
  }

  const kind = resolveNodeKind(entry.id, knownKinds)
  if (!kind) return { kind: null, isHidden: false, isDenied: false }

  return { kind, ...gateForKind(nodeKindByKind.get(kind)) }
}

/** A palette entry plus the presentation flags the list renderer needs. */
export type GatedPaletteEntry<T extends GateablePaletteEntry> = T & {
  isDisabled?: boolean
  disabledTooltip?: string
}

/**
 * Drop kill-switched palette entries and mark denied ones as disabled.
 *
 * @param entries Palette entries in display order.
 * @param nodeKindByKind Registry entries from `GET /node_kinds`, keyed by kind.
 * @returns The entries that stay visible, denied ones carrying `isDisabled`.
 */
export function gatePaletteEntries<T extends GateablePaletteEntry>(
  entries: readonly T[],
  nodeKindByKind: ReadonlyMap<string, NodeKind>
): GatedPaletteEntry<T>[] {
  if (nodeKindByKind.size === 0) return entries.map((entry) => ({ ...entry }))

  return entries.reduce<GatedPaletteEntry<T>[]>((visible, entry) => {
    const gate = gatePaletteEntry(entry, nodeKindByKind)
    if (gate.isHidden) return visible

    visible.push(
      gate.isDenied
        ? {
            ...entry,
            isDisabled: true,
            disabledTooltip: nodeKindDeniedTooltip(gate.kind ?? entry.id),
          }
        : { ...entry }
    )
    return visible
  }, [])
}
