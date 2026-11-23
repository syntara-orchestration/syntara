import { beforeEach, describe, expect, it, vi } from 'vitest'

import { copyWorkflowGraph, type SourceDefinition } from './copyWorkflowGraph'

// Deterministic ids: activity_1, activity_2, ... in node order.
let counter = 0
vi.mock('../../../../utils/generateUUID', () => ({
  generateActivityId: () => `activity_${++counter}`,
}))

// edgeHelpers port→handle mapping is reused as-is; keep the real implementation but
// guard against path/typing drift by asserting on the mapped handle shape loosely.
beforeEach(() => {
  counter = 0
})

const baseDef: SourceDefinition = {
  triggers: [{ id: 'trigger_0', type: 'subworkflow_trigger' }],
  nodes: [
    { id: 'task_a', type: 'script', parameters: { cmd: 'echo hi' }, position: { x: 0, y: 0 } },
    { id: 'task_b', type: 'http_request', parameters: { url: '${task_a.outputs.host}' }, position: { x: 200, y: 0 } },
  ],
  edges: [
    { from: 'trigger_0', to: 'task_a' }, // trigger edge → dropped
    { from: 'task_a', to: 'task_b' }, // internal edge → remapped
  ],
}

describe('copyWorkflowGraph', () => {
  it('copies non-trigger nodes with fresh unique ids and excludes triggers', () => {
    const r = copyWorkflowGraph(baseDef)
    expect(r.activities.map((a) => a.id)).toEqual(['activity_1', 'activity_2'])
    expect(new Set(r.activities.map((a) => a.id)).size).toBe(2) // unique
    // no trigger copied
    expect(r.activities.some((a) => (a as { type?: string }).type === 'subworkflow_trigger')).toBe(false)
  })

  it('remaps internal edges and drops edges touching an excluded trigger', () => {
    const r = copyWorkflowGraph(baseDef)
    expect(r.droppedEdgeCount).toBe(1)
    expect(r.edges).toHaveLength(1)
    expect(r.edges[0]).toMatchObject({ source: 'activity_1', target: 'activity_2' })
  })

  it('rewrites internal expression references to the new ids', () => {
    const r = copyWorkflowGraph(baseDef)
    const b = r.activities.find((a) => a.id === 'activity_2') as { parameters?: { url?: string } }
    expect(b.parameters?.url).toBe('${activity_1.outputs.host}')
  })

  it('offsets copied node positions and tracks them separately', () => {
    const r = copyWorkflowGraph(baseDef, { positionOffset: { x: 50, y: 50 } })
    expect(r.positions['activity_1']).toEqual({ x: 50, y: 50 })
    expect(r.positions['activity_2']).toEqual({ x: 250, y: 50 })
  })

  it('does not mutate the source definition', () => {
    const snapshot = JSON.parse(JSON.stringify(baseDef)) as typeof baseDef
    copyWorkflowGraph(baseDef)
    expect(baseDef).toEqual(snapshot)
  })

  it('detects project-scoped resource references without stripping or preserving silently', () => {
    const def: SourceDefinition = {
      nodes: [
        { id: 'job', type: 'aap_job_template', parameters: { credential_id: 'cred-1', integration_id: 'int-9' } },
        { id: 'plain', type: 'script', parameters: { cmd: 'x' } },
      ],
      edges: [],
    }
    const r = copyWorkflowGraph(def)
    expect(r.resourceReferenceNodes).toEqual([{ nodeId: 'activity_1', fields: ['credential_id', 'integration_id'] }])
    // The reference value is PRESERVED (not silently stripped); the caller surfaces + gates it.
    const job = r.activities.find((a) => a.id === 'activity_1') as { parameters?: Record<string, unknown> }
    expect(job.parameters?.credential_id).toBe('cred-1')
  })

  it('reports dangling expression refs to excluded trigger nodes', () => {
    const def: SourceDefinition = {
      triggers: [{ id: 'trigger_0', type: 'subworkflow_trigger' }],
      nodes: [{ id: 'task_a', type: 'script', parameters: { v: '${trigger_0.payload}' } }],
      edges: [],
    }
    const r = copyWorkflowGraph(def)
    expect(r.danglingExpressionRefs).toEqual([
      { nodeId: 'activity_1', namespace: 'trigger_0', expression: '${trigger_0.payload}' },
    ])
  })

  it('flags copied sub_workflow nodes so the caller can surface them (P1)', () => {
    const def: SourceDefinition = {
      triggers: [],
      nodes: [
        { id: 'task_a', type: 'script', parameters: {} },
        { id: 'child_ref', type: 'sub_workflow', parameters: { workflow_id: 'wf-1', trigger_node_id: 'tr-1' } },
      ],
      edges: [],
    }
    const r = copyWorkflowGraph(def)
    expect(r.subWorkflowNodes).toEqual([{ nodeId: 'activity_2' }])
  })

  it('preserves a copied sub_workflow node: target ids intact, input expressions remapped', () => {
    const def: SourceDefinition = {
      triggers: [],
      nodes: [
        { id: 'fetch', type: 'script', parameters: { cmd: 'x' } },
        {
          id: 'child_ref',
          type: 'sub_workflow',
          parameters: {
            workflow_id: 'wf-child',
            trigger_node_id: 'subworkflow_trigger_1',
            input_mapping: { host: '${fetch.outputs.host}' },
          },
        },
      ],
      edges: [{ from: 'fetch', to: 'child_ref' }],
    }
    const r = copyWorkflowGraph(def)
    const ref = r.activities.find((a) => a.id === 'activity_2') as {
      type?: string
      parameters?: { workflow_id?: string; trigger_node_id?: string; input_mapping?: Record<string, string> }
    }
    // reference node is copied as an ordinary activity with a fresh id
    expect(ref.type).toBe('sub_workflow')
    // target child + selected trigger are preserved verbatim (never remapped)
    expect(ref.parameters?.workflow_id).toBe('wf-child')
    expect(ref.parameters?.trigger_node_id).toBe('subworkflow_trigger_1')
    // internal input expression is remapped to the copied node id
    expect(ref.parameters?.input_mapping?.host).toBe('${activity_1.outputs.host}')
    // still surfaced (informational) and introduces no credential/integration block
    expect(r.subWorkflowNodes).toEqual([{ nodeId: 'activity_2' }])
    expect(r.resourceReferenceNodes).toEqual([])
  })

  it('preserves multiple sub_workflow references with their distinct targets', () => {
    const def: SourceDefinition = {
      triggers: [],
      nodes: [
        { id: 'r1', type: 'sub_workflow', parameters: { workflow_id: 'wf-1', trigger_node_id: 't1' } },
        { id: 'r2', type: 'sub_workflow', parameters: { workflow_id: 'wf-2', trigger_node_id: 't2' } },
      ],
      edges: [],
    }
    const r = copyWorkflowGraph(def)
    expect(r.subWorkflowNodes).toEqual([{ nodeId: 'activity_1' }, { nodeId: 'activity_2' }])
    expect(r.activities.map((a) => (a as { parameters?: { workflow_id?: string } }).parameters?.workflow_id)).toEqual([
      'wf-1',
      'wf-2',
    ])
  })

  it('remaps expressions inside condition and for_each control nodes to copied ids', () => {
    const def: SourceDefinition = {
      triggers: [],
      nodes: [
        { id: 'src', type: 'script', parameters: {} },
        { id: 'cond', type: 'condition', parameters: { condition: '${src.outputs.ok} == true' } },
        { id: 'loop', type: 'loop', parameters: { type: 'for_each', items: '${src.outputs.items}' } },
      ],
      edges: [],
    }
    const r = copyWorkflowGraph(def)
    const cond = r.activities.find((a) => a.id === 'activity_2') as { parameters?: { condition?: string } }
    const loop = r.activities.find((a) => a.id === 'activity_3') as { parameters?: { items?: string } }
    expect(cond.parameters?.condition).toBe('${activity_1.outputs.ok} == true')
    expect(loop.parameters?.items).toBe('${activity_1.outputs.items}')
  })

  it('reports no sub_workflow nodes for an ordinary source', () => {
    expect(copyWorkflowGraph(baseDef).subWorkflowNodes).toEqual([])
  })

  it('detects nested resource references inside integration_connections (P2)', () => {
    const def: SourceDefinition = {
      triggers: [],
      nodes: [
        {
          id: 'agent',
          type: 'agentic',
          parameters: {
            integration_connections: [
              { integration_id: 'int-1', credential_id: 'cred-1' },
              { integration_id: '', credential_id: null },
            ],
          },
        },
      ],
      edges: [],
    }
    const r = copyWorkflowGraph(def)
    expect(r.subWorkflowNodes).toEqual([])
    expect(r.resourceReferenceNodes).toHaveLength(1)
    expect(r.resourceReferenceNodes[0].nodeId).toBe('activity_1')
    expect(r.resourceReferenceNodes[0].fields).toEqual(
      expect.arrayContaining(['integration_connections[0].integration_id', 'integration_connections[0].credential_id'])
    )
    // empty nested refs are not flagged
    expect(r.resourceReferenceNodes[0].fields).not.toContain('integration_connections[1].credential_id')
  })
})
