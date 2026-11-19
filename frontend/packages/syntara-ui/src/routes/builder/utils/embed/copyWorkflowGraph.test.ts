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
})
