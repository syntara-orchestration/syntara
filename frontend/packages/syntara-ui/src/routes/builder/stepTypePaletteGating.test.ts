import { describe, expect, it } from 'vitest'

import { RegistryStepId } from '../../constants/registryStepIds'
import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import {
  STEP_TYPE_NO_PROJECT_TOOLTIP,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
  filterRestrictedEntries,
  gatePaletteEntries,
  gatePaletteEntry,
  stepTypeBlockedTooltip,
} from './stepTypePaletteGating'

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return {
    category: 'action',
    can_write: true,
    blocked_by: null,
    ...overrides,
  }
}

function registry(...entries: NodeKind[]): ReadonlyMap<string, NodeKind> {
  return new Map(entries.map((entry) => [entry.kind, entry]))
}

const allKinds = registry(
  kind({ kind: 'script' }),
  kind({ kind: 'http_request' }),
  kind({ kind: 'agentic' }),
  kind({ kind: 'approval' }),
  kind({ kind: 'condition', category: 'flow_control' }),
  kind({ kind: 'converge', category: 'flow_control' }),
  kind({ kind: 'loop', category: 'flow_control' }),
  kind({ kind: 'switch', category: 'flow_control' }),
  kind({ kind: 'wait', category: 'flow_control' }),
  kind({ kind: 'manual_trigger', category: 'trigger' }),
  kind({ kind: 'scheduled_trigger', category: 'trigger' })
)

const scriptDeny = {
  kind: 'script',
  label: 'Script',
} as const

describe('gatePaletteEntry', () => {
  it('resolves the step type a leaf palette entry creates', () => {
    expect(gatePaletteEntry({ id: RegistryStepId.ACTION_API }, allKinds)).toEqual({
      kind: 'http_request',
      isBlocked: false,
      blockedBy: null,
    })
  })

  it('marks a kind the caller may not write as blocked but visible', () => {
    const kinds = registry(kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }))

    expect(gatePaletteEntry({ id: RegistryStepId.ACTION_SCRIPT }, kinds)).toEqual({
      kind: 'script',
      isBlocked: true,
      blockedBy: scriptDeny,
    })
  })

  it('treats a container entry as ungated while any subtype is usable', () => {
    const kinds = registry(kind({ kind: 'script' }), kind({ kind: 'http_request', can_write: false }))

    expect(
      gatePaletteEntry(
        {
          id: RegistryStepId.ACTION,
          subtypes: [{ id: RegistryStepId.ACTION_SCRIPT }, { id: RegistryStepId.ACTION_API }],
        },
        kinds
      )
    ).toEqual({ kind: null, isBlocked: false, blockedBy: null })
  })

  it('disables a container entry only when every subtype is blocked', () => {
    const kinds = registry(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request', can_write: false, blocked_by: scriptDeny })
    )

    expect(
      gatePaletteEntry(
        {
          id: RegistryStepId.ACTION,
          subtypes: [{ id: RegistryStepId.ACTION_SCRIPT }, { id: RegistryStepId.ACTION_API }],
        },
        kinds
      )
    ).toMatchObject({ kind: null, isBlocked: true })
  })

  it('leaves entries with no backend kind untouched', () => {
    expect(gatePaletteEntry({ id: RegistryStepId.GENERIC }, allKinds)).toEqual({
      kind: null,
      isBlocked: false,
      blockedBy: null,
    })
  })

  it('fails closed when the permissions are unavailable', () => {
    expect(gatePaletteEntry({ id: RegistryStepId.ACTION_SCRIPT }, allKinds, true)).toEqual({
      kind: null,
      isBlocked: true,
      blockedBy: null,
    })
  })
})

describe('gatePaletteEntries', () => {
  const entries = [
    { id: RegistryStepId.ACTION_SCRIPT },
    { id: RegistryStepId.ACTION_API },
    { id: RegistryStepId.AGENT },
  ]

  it('keeps every entry visible and preserves display order', () => {
    const kinds = registry(
      kind({ kind: 'script' }),
      kind({ kind: 'http_request', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'agentic' })
    )

    expect(gatePaletteEntries(entries, kinds).map((entry) => entry.id)).toEqual([
      RegistryStepId.ACTION_SCRIPT,
      RegistryStepId.ACTION_API,
      RegistryStepId.AGENT,
    ])
  })

  it('attaches the permission-denied tooltip to blocked entries', () => {
    const kinds = registry(
      kind({ kind: 'script', can_write: false, blocked_by: scriptDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )

    const gated = gatePaletteEntries(entries, kinds)

    expect(gated[0]).toMatchObject({
      isDisabled: true,
      disabledTooltip: "You don't have permission to write Script steps.",
    })
    expect(gated[1].isDisabled).toBeUndefined()
  })

  it('disables every entry when the permissions are unavailable', () => {
    const gated = gatePaletteEntries(entries, new Map(), true)

    expect(gated).toHaveLength(entries.length)
    for (const entry of gated) {
      expect(entry.isDisabled).toBe(true)
      expect(entry.disabledTooltip).toBe(STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP)
    }
  })

  it('uses the given tooltip when failing closed for another reason, such as no project', () => {
    const gated = gatePaletteEntries(entries, new Map(), true, STEP_TYPE_NO_PROJECT_TOOLTIP)

    for (const entry of gated) {
      expect(entry.isDisabled).toBe(true)
      expect(entry.disabledTooltip).toBe(STEP_TYPE_NO_PROJECT_TOOLTIP)
    }
  })

  it('renders entries unchanged when nothing is blocked', () => {
    const gated = gatePaletteEntries(entries, allKinds)
    expect(gated.map((entry) => entry.id)).toEqual(entries.map((entry) => entry.id))
    expect(gated.every((entry) => entry.isDisabled !== true)).toBe(true)
  })
})

describe('filterRestrictedEntries', () => {
  const gated = [
    { id: 'script', isDisabled: true, disabledTooltip: 'Blocked by p (all projects)' },
    { id: 'http_request' },
    { id: 'agentic', isDisabled: true, disabledTooltip: 'Blocked by p (all projects)' },
  ]

  it('hides restricted entries by default and counts them', () => {
    const { entries, restrictedCount } = filterRestrictedEntries(gated, false)

    expect(entries.map((entry) => entry.id)).toEqual(['http_request'])
    expect(restrictedCount).toBe(2)
  })

  it('keeps restricted entries in display order when revealed', () => {
    const { entries, restrictedCount } = filterRestrictedEntries(gated, true)

    expect(entries.map((entry) => entry.id)).toEqual(['script', 'http_request', 'agentic'])
    expect(restrictedCount).toBe(2)
  })

  it('reports no restricted entries when nothing is blocked', () => {
    expect(filterRestrictedEntries([{ id: 'script' }], false)).toEqual({
      entries: [{ id: 'script' }],
      restrictedCount: 0,
    })
  })
})

describe('stepTypeBlockedTooltip', () => {
  it('names the step type only, never the policy or scope (AC-3.g, R11)', () => {
    expect(stepTypeBlockedTooltip(scriptDeny)).toBe("You don't have permission to write Script steps.")
  })
})
