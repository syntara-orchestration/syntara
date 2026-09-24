import { describe, expect, it } from 'vitest'

import { RegistryNodeId } from '../../../constants'

import { NODE_KIND_BY_REGISTRY_ID, resolveNodeKind } from './nodeKindMapping'

const backendKinds: ReadonlySet<string> = new Set([
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
  'mcp_tool',
  'script',
])

describe('NODE_KIND_BY_REGISTRY_ID', () => {
  it('maps every mapped registry id to a kind the backend registry knows', () => {
    for (const kind of Object.values(NODE_KIND_BY_REGISTRY_ID)) {
      expect(backendKinds.has(kind)).toBe(true)
    }
  })

  it('does not map container entries that only open a subtype list', () => {
    for (const containerId of [
      RegistryNodeId.TRIGGER,
      RegistryNodeId.ACTION,
      RegistryNodeId.LOGIC,
      RegistryNodeId.AAP_EXECUTION,
      RegistryNodeId.GENERIC,
    ]) {
      expect(NODE_KIND_BY_REGISTRY_ID[containerId]).toBeUndefined()
    }
  })
})

describe('resolveNodeKind', () => {
  it.each([
    [RegistryNodeId.TRIGGER_MANUAL, 'manual_trigger'],
    [RegistryNodeId.TRIGGER_SCHEDULED, 'scheduled_trigger'],
    [RegistryNodeId.TRIGGER_WEBHOOK, 'webhook_trigger'],
    [RegistryNodeId.TRIGGER_EDA, 'eda_trigger'],
    [RegistryNodeId.ACTION_SCRIPT, 'script'],
    [RegistryNodeId.ACTION_API, 'http_request'],
    [RegistryNodeId.APPROVAL, 'approval'],
    [RegistryNodeId.AGENT, 'agentic'],
    [RegistryNodeId.LOGIC_CONDITION, 'condition'],
    [RegistryNodeId.LOGIC_CONVERGE, 'converge'],
    [RegistryNodeId.LOGIC_LOOP, 'loop'],
    [RegistryNodeId.LOGIC_SWITCH, 'switch'],
    [RegistryNodeId.LOGIC_WAIT, 'wait'],
    [RegistryNodeId.ACTION_MCP_TOOL, 'mcp_tool'],
    [RegistryNodeId.AAP_JOB_TEMPLATE, 'aap_job_template'],
    [RegistryNodeId.AAP_WORKFLOW_TEMPLATE, 'aap_workflow_job_template'],
  ])('maps %s to %s', (registryId, expected) => {
    expect(resolveNodeKind(registryId, backendKinds)).toBe(expected)
  })

  it.each([RegistryNodeId.TRIGGER, RegistryNodeId.ACTION, RegistryNodeId.LOGIC, RegistryNodeId.AAP_EXECUTION])(
    'returns null for the container entry %s',
    (registryId) => {
      expect(resolveNodeKind(registryId, backendKinds)).toBeNull()
    }
  )

  it('returns null for the placeholder entry', () => {
    expect(resolveNodeKind(RegistryNodeId.GENERIC, backendKinds)).toBeNull()
  })

  it('normalizes an unmapped registry id when the backend knows the resulting kind', () => {
    expect(resolveNodeKind('action-internal-activity', backendKinds)).toBe('internal_activity')
  })

  it('returns null when normalization does not land on a known kind', () => {
    expect(resolveNodeKind('action-something-else', backendKinds)).toBeNull()
  })
})
