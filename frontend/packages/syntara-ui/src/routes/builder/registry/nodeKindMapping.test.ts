import { ActivityTypeEnum, TriggerTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { RegistryNodeId } from '../../../constants'

import { nodeKindByRegistryId, resolveNodeKind } from './nodeKindMapping'

/** Container ids and the programmatic-only generic entry have no node kind. */
const IDS_WITHOUT_KIND = new Set<string>([
  RegistryNodeId.TRIGGER,
  RegistryNodeId.ACTION,
  RegistryNodeId.LOGIC,
  RegistryNodeId.AAP_EXECUTION,
  RegistryNodeId.GENERIC,
])

describe('resolveNodeKind', () => {
  it('resolves every palette entry registry id to a node kind', () => {
    for (const id of Object.values(RegistryNodeId)) {
      if (IDS_WITHOUT_KIND.has(id)) {
        continue
      }
      expect(resolveNodeKind(id)).not.toBeNull()
    }
  })

  it('resolves container, generic, and unknown ids to null', () => {
    for (const id of IDS_WITHOUT_KIND) {
      expect(resolveNodeKind(id)).toBeNull()
    }
    expect(resolveNodeKind('not-a-registry-id')).toBeNull()
  })

  it('resolves representative ids to their backend node kind', () => {
    expect(resolveNodeKind(RegistryNodeId.TRIGGER_MANUAL)).toBe(TriggerTypeEnum.MANUAL_TRIGGER)
    expect(resolveNodeKind(RegistryNodeId.ACTION_SCRIPT)).toBe(ActivityTypeEnum.SCRIPT)
    expect(resolveNodeKind(RegistryNodeId.LOGIC_CONDITION)).toBe(ActivityTypeEnum.CONDITION)
    expect(resolveNodeKind(RegistryNodeId.AGENT)).toBe(ActivityTypeEnum.AGENTIC)
    expect(resolveNodeKind(RegistryNodeId.AAP_WORKFLOW_TEMPLATE)).toBe(ActivityTypeEnum.AAP_WORKFLOW_JOB_TEMPLATE)
  })
})

describe('nodeKindByRegistryId', () => {
  it('keys every entry with a valid RegistryNodeId value', () => {
    // The contracts table is keyed by string literals; this catches typos
    const validIds = new Set<string>(Object.values(RegistryNodeId))
    for (const key of Object.keys(nodeKindByRegistryId)) {
      expect(validIds.has(key)).toBe(true)
    }
  })
})
