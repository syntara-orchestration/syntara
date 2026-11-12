import { describe, expect, it } from 'vitest'

import { RegistryStepId } from '../../constants'
import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import {
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
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

const projectDeny = {
  kind: 'script',
  label: 'Script',
  reason: 'explicit_deny',
  policy: 'no-scripts-in-payments',
  scope: 'project',
  project: 'payments',
} as const

const globalDeny = {
  kind: 'script',
  label: 'Script',
  reason: 'explicit_deny',
  policy: 'no-scripts-anywhere',
  scope: 'any',
  project: null,
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
    const kinds = registry(kind({ kind: 'script', can_write: false, blocked_by: projectDeny }))

    expect(gatePaletteEntry({ id: RegistryStepId.ACTION_SCRIPT }, kinds)).toEqual({
      kind: 'script',
      isBlocked: true,
      blockedBy: projectDeny,
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
      kind({ kind: 'script', can_write: false, blocked_by: projectDeny }),
      kind({ kind: 'http_request', can_write: false, blocked_by: globalDeny })
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
      kind({ kind: 'http_request', can_write: false, blocked_by: globalDeny }),
      kind({ kind: 'agentic' })
    )

    expect(gatePaletteEntries(entries, kinds).map((entry) => entry.id)).toEqual([
      RegistryStepId.ACTION_SCRIPT,
      RegistryStepId.ACTION_API,
      RegistryStepId.AGENT,
    ])
  })

  it('attaches a tooltip naming the policy and scope to blocked entries', () => {
    const kinds = registry(
      kind({ kind: 'script', can_write: false, blocked_by: projectDeny }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )

    const gated = gatePaletteEntries(entries, kinds)

    expect(gated[0]).toMatchObject({
      isDisabled: true,
      disabledTooltip: 'Blocked by no-scripts-in-payments (project payments)',
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

  it('renders entries unchanged when nothing is blocked', () => {
    const gated = gatePaletteEntries(entries, allKinds)
    expect(gated.map((entry) => entry.id)).toEqual(entries.map((entry) => entry.id))
    expect(gated.every((entry) => entry.isDisabled !== true)).toBe(true)
  })
})

describe('stepTypeBlockedTooltip', () => {
  it('names the policy and project scope of an explicit deny', () => {
    expect(stepTypeBlockedTooltip(projectDeny)).toBe('Blocked by no-scripts-in-payments (project payments)')
  })

  it('names the policy and global scope of an explicit deny', () => {
    expect(stepTypeBlockedTooltip(globalDeny)).toBe('Blocked by no-scripts-anywhere (all projects)')
  })

  it('explains a missing allow instead of naming a denying policy', () => {
    expect(
      stepTypeBlockedTooltip({
        kind: 'script',
        label: 'Script',
        reason: 'no_matching_allow',
        policy: null,
        scope: null,
        project: 'payments',
      })
    ).toBe('No policy grants write permission for Script in project payments')
  })

  it('omits the project when the evaluated project is unknown', () => {
    expect(
      stepTypeBlockedTooltip({
        kind: 'script',
        label: 'Script',
        reason: 'no_matching_allow',
        policy: null,
        scope: null,
        project: null,
      })
    ).toBe('No policy grants write permission for Script')
  })
})
