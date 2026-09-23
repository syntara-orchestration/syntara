import { describe, expect, it } from 'vitest'

import { RegistryNodeId } from '../../constants'
import type { NodeKind } from '../../hooks/useNodeKindsQuery'

import { gatePaletteEntries, gatePaletteEntry, nodeKindDeniedTooltip } from './nodeKindPaletteGating'

function kind(overrides: Partial<NodeKind> & { kind: string }): NodeKind {
  return {
    category: 'action',
    enabled: true,
    switchable: true,
    deniable_actions: ['write', 'execute'],
    can_write: true,
    attributes: [],
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
  kind({ kind: 'condition', category: 'flow_control', switchable: false, deniable_actions: [] }),
  kind({ kind: 'converge', category: 'flow_control', switchable: false, deniable_actions: [] }),
  kind({ kind: 'loop', category: 'flow_control', switchable: false, deniable_actions: [] }),
  kind({ kind: 'switch', category: 'flow_control', switchable: false, deniable_actions: [] }),
  kind({ kind: 'wait', category: 'flow_control', switchable: false, deniable_actions: [] }),
  kind({ kind: 'manual_trigger', category: 'trigger', deniable_actions: ['write'] }),
  kind({ kind: 'scheduled_trigger', category: 'trigger', deniable_actions: ['write'] })
)

describe('gatePaletteEntry', () => {
  it('resolves the node kind a leaf palette entry creates', () => {
    expect(gatePaletteEntry({ id: RegistryNodeId.ACTION_API }, allKinds)).toEqual({
      kind: 'http_request',
      isHidden: false,
      isDenied: false,
    })
  })

  it('hides a kind that is switched off platform-wide', () => {
    const kinds = registry(kind({ kind: 'agentic', enabled: false }))

    expect(gatePaletteEntry({ id: RegistryNodeId.AGENT }, kinds)).toMatchObject({ isHidden: true })
  })

  it('marks a kind the caller may not write as denied but not hidden', () => {
    const kinds = registry(kind({ kind: 'script', can_write: false }))

    expect(gatePaletteEntry({ id: RegistryNodeId.ACTION_SCRIPT }, kinds)).toEqual({
      kind: 'script',
      isHidden: false,
      isDenied: true,
    })
  })

  it('treats a container entry as ungated while any subtype is usable', () => {
    const kinds = registry(kind({ kind: 'script', enabled: false }), kind({ kind: 'http_request' }))

    expect(
      gatePaletteEntry(
        {
          id: RegistryNodeId.ACTION,
          subtypes: [{ id: RegistryNodeId.ACTION_SCRIPT }, { id: RegistryNodeId.ACTION_API }],
        },
        kinds
      )
    ).toEqual({ kind: null, isHidden: false, isDenied: false })
  })

  it('hides a container entry when every subtype is switched off', () => {
    const kinds = registry(kind({ kind: 'script', enabled: false }), kind({ kind: 'http_request', enabled: false }))

    expect(
      gatePaletteEntry(
        {
          id: RegistryNodeId.ACTION,
          subtypes: [{ id: RegistryNodeId.ACTION_SCRIPT }, { id: RegistryNodeId.ACTION_API }],
        },
        kinds
      )
    ).toMatchObject({ isHidden: true })
  })

  it('disables a container entry when every remaining subtype is denied', () => {
    const kinds = registry(kind({ kind: 'script', enabled: false }), kind({ kind: 'http_request', can_write: false }))

    expect(
      gatePaletteEntry(
        {
          id: RegistryNodeId.ACTION,
          subtypes: [{ id: RegistryNodeId.ACTION_SCRIPT }, { id: RegistryNodeId.ACTION_API }],
        },
        kinds
      )
    ).toMatchObject({ isHidden: false, isDenied: true })
  })

  it('leaves entries with no backend kind untouched', () => {
    expect(gatePaletteEntry({ id: RegistryNodeId.GENERIC }, allKinds)).toEqual({
      kind: null,
      isHidden: false,
      isDenied: false,
    })
  })

  it('resolves a newly registered kind from its registry id', () => {
    const kinds = registry(kind({ kind: 'custom_step', category: 'flow_control', switchable: false }))

    expect(gatePaletteEntry({ id: 'logic-custom-step' }, kinds)).toMatchObject({ kind: 'custom_step' })
  })
})

describe('gatePaletteEntries', () => {
  const entries = [
    { id: RegistryNodeId.ACTION_SCRIPT },
    { id: RegistryNodeId.ACTION_API },
    { id: RegistryNodeId.AGENT },
  ]

  it('drops hidden entries and keeps display order', () => {
    const kinds = registry(
      kind({ kind: 'script' }),
      kind({ kind: 'http_request', enabled: false }),
      kind({ kind: 'agentic' })
    )

    expect(gatePaletteEntries(entries, kinds).map((entry) => entry.id)).toEqual([
      RegistryNodeId.ACTION_SCRIPT,
      RegistryNodeId.AGENT,
    ])
  })

  it('attaches a tooltip to denied entries and leaves allowed entries clean', () => {
    const kinds = registry(
      kind({ kind: 'script', can_write: false }),
      kind({ kind: 'http_request' }),
      kind({ kind: 'agentic' })
    )

    const gated = gatePaletteEntries(entries, kinds)

    expect(gated[0]).toMatchObject({
      isDisabled: true,
      disabledTooltip: 'You are not allowed to add script nodes',
    })
    expect(gated[1].isDisabled).toBeUndefined()
  })

  it('renders every entry unchanged before the registry has loaded', () => {
    expect(gatePaletteEntries(entries, new Map())).toEqual(entries)
  })
})

describe('nodeKindDeniedTooltip', () => {
  it('names the node kind that is denied', () => {
    expect(nodeKindDeniedTooltip('mcp_tool')).toBe('You are not allowed to add mcp_tool nodes')
  })
})
