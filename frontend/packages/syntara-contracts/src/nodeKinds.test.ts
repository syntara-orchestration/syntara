import { describe, expect, it } from 'vitest'

import { NODE_KIND_BY_REGISTRY_ID } from './nodeKinds'

/**
 * Every backend `NodeType` value. Mirrors `syntara.workflows.node_kinds`
 * on the backend — keep in sync when a step type is added or removed.
 */
const KNOWN_KINDS = new Set([
  'manual_trigger',
  'scheduled_trigger',
  'webhook_trigger',
  'eda_trigger',
  'condition',
  'converge',
  'loop',
  'switch',
  'wait',
  'aap_job_template',
  'aap_workflow_job_template',
  'agentic',
  'approval',
  'http_request',
  'internal_activity',
  'script',
])

/**
 * Node kinds with no builder palette entry, so no registry id maps to them.
 * `internal_activity` nodes are created only programmatically.
 */
const KINDS_WITHOUT_PALETTE_ENTRY = new Set(['internal_activity'])

/** Container ids open a subtype list; `generic` is programmatic-only. */
const IDS_WITHOUT_KIND = new Set(['trigger', 'action', 'logic', 'aap-execution', 'generic'])

describe('NODE_KIND_BY_REGISTRY_ID', () => {
  it('maps every registry id to a known backend node kind', () => {
    for (const kind of Object.values(NODE_KIND_BY_REGISTRY_ID)) {
      expect(KNOWN_KINDS.has(kind)).toBe(true)
    }
  })

  it('never maps to the pseudo trigger type event', () => {
    // TriggerTypeEnum.EVENT ('event') is a UI-only discriminator, not a backend NodeType
    expect(Object.values(NODE_KIND_BY_REGISTRY_ID)).not.toContain('event')
  })

  it('maps every known node kind except the allowlisted palette-less kinds', () => {
    const mapped = new Set(Object.values(NODE_KIND_BY_REGISTRY_ID))
    const unmapped = [...KNOWN_KINDS].filter((kind) => !mapped.has(kind))
    expect(unmapped).toEqual([...KINDS_WITHOUT_PALETTE_ENTRY])
  })

  it('maps each node kind at most once', () => {
    const values = Object.values(NODE_KIND_BY_REGISTRY_ID)
    expect(new Set(values).size).toBe(values.length)
  })

  it('does not map container or programmatic-only registry ids', () => {
    for (const id of Object.keys(NODE_KIND_BY_REGISTRY_ID)) {
      expect(IDS_WITHOUT_KIND.has(id)).toBe(false)
    }
  })
})
