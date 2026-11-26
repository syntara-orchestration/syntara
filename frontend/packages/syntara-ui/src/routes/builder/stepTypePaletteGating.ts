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
  /** The caller may not author this step type — the entry is hidden by default, or shown inert. */
  isBlocked: boolean
  /** Why the step type is blocked, when it is. */
  blockedBy: BlockedStepType | null
}

/**
 * Tooltip shown on a palette entry the caller may not add.
 *
 * The prototype sentence, naming the step type only: policy names and scopes
 * belong in audit events, never in caller-facing copy (AC-3.g, R11).
 */
export function stepTypeBlockedTooltip(blockedBy: BlockedStepType): string {
  return `You don't have permission to write ${blockedBy.label} steps.`
}

/**
 * Message shown when pasting or duplicating a blocked step type on the canvas
 * is refused. Same wording as the palette tooltip for the blocked kind.
 */
export function stepTypeBlockedMessage(blockedBy: BlockedStepType): string {
  return stepTypeBlockedTooltip(blockedBy)
}

/**
 * The same message for several blocked step types at once, so the caller sees
 * every type in one pass: "Script", "Script and Approval", "Script, Approval and Email".
 */
export function stepTypesBlockedMessage(blocked: readonly BlockedStepType[]): string {
  const labels = blocked.map(({ label }) => label)
  const joined = labels.length > 1 ? `${labels.slice(0, -1).join(', ')} and ${labels.at(-1)}` : labels.join('')
  return `You don't have permission to write ${joined} steps.`
}

/** Message shown when a canvas action is refused because the permissions are still loading. */
export const STEP_TYPE_PERMISSIONS_LOADING_MESSAGE = 'Step type permissions are still loading. Try again in a moment.'

/** Tooltip shown on every entry when the permissions endpoint is unavailable. */
export const STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP =
  'Step type permissions could not be loaded. Ask an administrator to check the server.'

/**
 * Tooltip shown on every entry when no project is selected.
 *
 * Step-type denies are evaluated per project, so without one the panel cannot
 * know what the caller may add and fails closed rather than allowing everything.
 */
export const STEP_TYPE_NO_PROJECT_TOOLTIP = 'Select a project to check step permissions'

function gateForKind(entry: NodeKind | undefined): { isBlocked: boolean; blockedBy: BlockedStepType | null } {
  if (!entry) return { isBlocked: false, blockedBy: null }
  return { isBlocked: !entry.can_write, blockedBy: entry.blocked_by ?? null }
}

/**
 * Decide, per palette entry, whether it must be shown disabled.
 *
 * A `step_type:write` deny (or a missing allow) blocks the entry: the panel
 * hides it by default and, when restricted steps are revealed, shows it inert
 * with an explanatory tooltip. Steps of that kind already on the canvas are
 * untouched.
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
 * Mark blocked palette entries as disabled.
 *
 * Every entry is returned; whether blocked ones are shown is the caller's
 * choice (see {@link filterRestrictedEntries}).
 *
 * @param entries Palette entries in display order.
 * @param nodeKindByKind Registry entries from `GET /node_kinds`, keyed by kind.
 * @param isUnavailable True when the permissions endpoint failed, returned nothing, or no project is selected.
 * @param unavailableTooltip Tooltip for entries disabled because the permissions are unavailable.
 * @returns The entries in display order, blocked ones carrying `isDisabled`.
 */
export function gatePaletteEntries<T extends GateablePaletteEntry>(
  entries: readonly T[],
  nodeKindByKind: ReadonlyMap<string, NodeKind>,
  isUnavailable = false,
  unavailableTooltip: string = STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP
): GatedPaletteEntry<T>[] {
  if (nodeKindByKind.size === 0 && !isUnavailable) return entries.map((entry) => ({ ...entry }))

  return entries.map((entry) => {
    const gate = gatePaletteEntry(entry, nodeKindByKind, isUnavailable)
    if (!gate.isBlocked) return { ...entry }

    return {
      ...entry,
      isDisabled: true,
      disabledTooltip: gate.blockedBy != null ? stepTypeBlockedTooltip(gate.blockedBy) : unavailableTooltip,
    }
  })
}

/**
 * Hide restricted (disabled) palette entries unless the author asked to see them.
 *
 * Denied step types are hidden from the toolbox by default; a toggle reveals
 * the full catalogue with those entries padlocked and inert.
 *
 * @param entries Gated palette entries in display order.
 * @param showRestricted True to keep restricted entries in the list.
 * @returns The entries to render and how many restricted entries the list holds.
 */
export function filterRestrictedEntries<T extends GateablePaletteEntry>(
  entries: readonly GatedPaletteEntry<T>[],
  showRestricted: boolean
): { entries: GatedPaletteEntry<T>[]; restrictedCount: number } {
  const restrictedCount = entries.filter((entry) => entry.isDisabled === true).length
  return {
    entries: showRestricted ? [...entries] : entries.filter((entry) => entry.isDisabled !== true),
    restrictedCount,
  }
}
