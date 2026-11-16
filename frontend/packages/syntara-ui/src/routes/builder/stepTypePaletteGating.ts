import type { BlockedStepType, NodeKind } from '../../hooks/useNodeKindsQuery'

/** Minimal palette entry shape the gate needs — a registry step type or one of its subtypes. */
export type GateablePaletteEntry = {
  id: string
  subtypes?: readonly { id: string }[]
}

/** Gating verdict for one palette entry. */
export type PaletteEntryGate = {
  /** The backend step type this entry creates, or `null` for container entries. */
  kind: string | null
  /** The caller may not author this step type — the entry stays visible but inert. */
  isBlocked: boolean
  /** Why the step type is blocked, when it is. */
  blockedBy: BlockedStepType | null
}

/**
 * Tooltip shown on a palette entry the caller may not add.
 *
 * An explicit deny names the policy and its scope; a missing allow explains
 * that no policy grants write permission in this project.
 */
export function stepTypeBlockedTooltip(blockedBy: BlockedStepType): string {
  if (blockedBy.reason === 'no_matching_allow') {
    const project = blockedBy.project ? ` in project ${blockedBy.project}` : ''
    return `No policy grants write permission for ${blockedBy.label}${project}`
  }
  const scope = blockedBy.scope === 'project' && blockedBy.project ? `project ${blockedBy.project}` : 'all projects'
  return `Blocked by ${blockedBy.policy ?? 'a policy'} (${scope})`
}

/** Tooltip shown on every entry when the permissions endpoint is unavailable. */
export const STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP =
  'Step type permissions could not be loaded. Ask an administrator to check the server.'

function gateForKind(entry: NodeKind | undefined): { isBlocked: boolean; blockedBy: BlockedStepType | null } {
  if (!entry) return { isBlocked: false, blockedBy: null }
  return { isBlocked: !entry.can_write, blockedBy: entry.blocked_by ?? null }
}

/**
 * Decide, per palette entry, whether it must be shown disabled.
 *
 * A `step_type:write` deny (or a missing allow) keeps the entry visible but
 * inert with an explanatory tooltip naming the policy and scope. Steps of that
 * kind already on the canvas are untouched.
 *
 * Container entries (`trigger`, `action`, `logic`, `aap-execution`) create no
 * step themselves; they inherit the verdict of their subtypes and are only
 * disabled when every subtype is blocked.
 *
 * When the permissions are unavailable the gate fails closed: every entry is
 * disabled with a tooltip explaining why, so the panel never claims
 * everything is allowed. The server still rejects the save.
 *
 * @param entry Palette entry, optionally carrying its subtypes.
 * @param nodeKindByKind Registry entries from `GET /node_kinds`, keyed by kind.
 * @param isUnavailable True when the permissions endpoint failed or returned nothing.
 * @returns The gating verdict for the entry.
 */
export function gatePaletteEntry(
  entry: GateablePaletteEntry,
  nodeKindByKind: ReadonlyMap<string, NodeKind>,
  isUnavailable = false
): PaletteEntryGate {
  if (isUnavailable) {
    return { kind: null, isBlocked: true, blockedBy: null }
  }

  if (entry.subtypes?.length) {
    const subtypeGates = entry.subtypes.map((subtype) => gateForKind(nodeKindByKind.get(subtype.id)))
    const allBlocked = subtypeGates.every((gate) => gate.isBlocked)
    const firstBlocked = subtypeGates.find((gate) => gate.isBlocked && gate.blockedBy) ?? null
    return { kind: null, isBlocked: allBlocked, blockedBy: allBlocked ? (firstBlocked?.blockedBy ?? null) : null }
  }

  // Palette ids are the backend kinds themselves; ids the endpoint did not
  // report (container entries, the generic placeholder) have no verdict.
  const nodeKind = nodeKindByKind.get(entry.id)
  if (!nodeKind) return { kind: null, isBlocked: false, blockedBy: null }

  return { kind: entry.id, ...gateForKind(nodeKind) }
}

/** A palette entry plus the presentation flags the list renderer needs. */
export type GatedPaletteEntry<T extends GateablePaletteEntry> = T & {
  isDisabled?: boolean
  disabledTooltip?: string
}

/**
 * Mark blocked palette entries as disabled; blocked entries stay visible.
 *
 * @param entries Palette entries in display order.
 * @param nodeKindByKind Registry entries from `GET /node_kinds`, keyed by kind.
 * @param isUnavailable True when the permissions endpoint failed or returned nothing.
 * @returns The entries that stay visible, blocked ones carrying `isDisabled`.
 */
export function gatePaletteEntries<T extends GateablePaletteEntry>(
  entries: readonly T[],
  nodeKindByKind: ReadonlyMap<string, NodeKind>,
  isUnavailable = false
): GatedPaletteEntry<T>[] {
  if (nodeKindByKind.size === 0 && !isUnavailable) return entries.map((entry) => ({ ...entry }))

  return entries.map((entry) => {
    const gate = gatePaletteEntry(entry, nodeKindByKind, isUnavailable)
    if (!gate.isBlocked) return { ...entry }

    return {
      ...entry,
      isDisabled: true,
      disabledTooltip:
        gate.blockedBy != null ? stepTypeBlockedTooltip(gate.blockedBy) : STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
    }
  })
}

/**
 * Message shown when pasting or duplicating a blocked step type on the canvas
 * is refused. Same wording as the palette tooltip for the blocked kind.
 */
export function stepTypeBlockedMessage(blockedBy: BlockedStepType): string {
  return stepTypeBlockedTooltip(blockedBy)
}
