import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { v4 as uuidv4 } from 'uuid'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'

/*
 * Regression coverage for the published-dependency "Used-By" semantics and the two
 * confirmation-required 409 flows (Comment #5). Everything is exercised through the public
 * mock endpoints (POST/PATCH/DELETE/GET over a real TCP socket) rather than the internal
 * helpers, so the handlers' request parsing, routing, gating, and response envelopes are all
 * covered end to end -- mirroring the existing handlers.*.test.ts infrastructure.
 */

let server: Server
let baseUrl: string

beforeAll(async () => {
  const app = createServer(...handlers) as unknown as { listen: (port: number) => Server }
  server = app.listen(0)
  await new Promise<void>((resolve, reject) => {
    server.once('listening', resolve)
    server.once('error', reject)
  })
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('mock API did not bind a TCP port')
  baseUrl = `http://127.0.0.1:${address.port}`
})

afterAll(async () => {
  await new Promise<void>((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())))
})

const JSON_HEADERS = { 'Content-Type': 'application/json' }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** POST /workflows with an arbitrary workflow_definition; returns the created workflow id. */
async function createWorkflow(workflowDefinition: Record<string, unknown>): Promise<string> {
  const name = `used-by-${uuidv4()}`
  const res = await fetch(`${baseUrl}/api/v1/workflows`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name, project_id: 'p-001', workflow_definition: { name, ...workflowDefinition } }),
  })
  expect(res.status).toBe(201)
  const created: unknown = await res.json()
  if (!isRecord(created) || typeof created.id !== 'string') throw new Error('create response missing id')
  return created.id
}

/** POST a version/publish; returns the raw Response so callers can assert status/body/headers. */
async function publish(workflowId: string, version: number, confirm?: boolean): Promise<Response> {
  const query = confirm === undefined ? '' : `?confirm=${String(confirm)}`
  return fetch(`${baseUrl}/api/v1/workflows/${workflowId}/versions/${version}/publish${query}`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ expected_version: version }),
  })
}

async function publishOk(workflowId: string, version: number): Promise<void> {
  const res = await publish(workflowId, version)
  expect(res.status).toBe(200)
}

/** PATCH /workflows/{id} with a new workflow_definition (creates the next draft version). */
async function patchDefinition(workflowId: string, workflowDefinition: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${baseUrl}/api/v1/workflows/${workflowId}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify({ workflow_definition: { name: `patch-${uuidv4()}`, ...workflowDefinition } }),
  })
  expect(res.status).toBe(200)
}

async function usedByCount(childId: string, triggerNodeIds: string[] = []): Promise<number> {
  const query = triggerNodeIds.map((t) => `trigger_node_ids=${encodeURIComponent(t)}`).join('&')
  const res = await fetch(`${baseUrl}/api/v1/workflows/${childId}/used_by${query ? `?${query}` : ''}`)
  expect(res.status).toBe(200)
  const body: unknown = await res.json()
  if (!isRecord(body) || typeof body.referencing_parent_count !== 'number') {
    throw new Error('used_by response missing referencing_parent_count')
  }
  return body.referencing_parent_count
}

async function batchCount(childId: string): Promise<number> {
  const res = await fetch(`${baseUrl}/api/v1/workflows/used_by_counts?workflow_ids=${childId}`)
  expect(res.status).toBe(200)
  const body: unknown = await res.json()
  if (!isRecord(body) || !Array.isArray(body.counts)) throw new Error('used_by_counts response missing counts')
  const row = body.counts.find((c): c is Record<string, unknown> => isRecord(c) && c.workflow_id === childId)
  if (!row || typeof row.referencing_parent_count !== 'number') throw new Error('child not found in batch counts')
  return row.referencing_parent_count
}

/** A plain child definition with no sub_workflow nodes and no subworkflow triggers. */
function plainDef(): Record<string, unknown> {
  return { schema_version: '2.0.0', triggers: [], nodes: [], edges: [] }
}

/** A parent definition with one sub_workflow node referencing `childId` via `triggerNodeId`. */
function parentDef(childId: string, triggerNodeId?: string): Record<string, unknown> {
  return {
    schema_version: '2.0.0',
    triggers: [],
    nodes: [
      {
        id: `call-${uuidv4()}`,
        type: 'sub_workflow',
        parameters: { workflow_id: childId, ...(triggerNodeId ? { trigger_node_id: triggerNodeId } : {}) },
      },
    ],
    edges: [],
  }
}

describe('Used-By: published-dependency discovery', () => {
  it('counts a published parent that references the child (single and batch agree)', async () => {
    const child = await createWorkflow(plainDef())
    const parent = await createWorkflow(parentDef(child))
    await publishOk(parent, 1)

    expect(await usedByCount(child)).toBe(1)
    expect(await batchCount(child)).toBe(1)
  })

  it('does not count a draft-only (unpublished) parent', async () => {
    const child = await createWorkflow(plainDef())
    await createWorkflow(parentDef(child)) // created but never published

    expect(await usedByCount(child)).toBe(0)
    expect(await batchCount(child)).toBe(0)
  })

  it('reflects the PUBLISHED version, not a later draft that removes the reference', async () => {
    const child = await createWorkflow(plainDef())
    const parent = await createWorkflow(parentDef(child))
    await publishOk(parent, 1)
    expect(await usedByCount(child)).toBe(1)

    // Draft edit removes the sub_workflow node, but the draft is not published.
    await patchDefinition(parent, plainDef())
    expect(await usedByCount(child)).toBe(1) // published v1 still references the child
  })

  it('counts a parent once even when it references the child via multiple sub_workflow nodes', async () => {
    const child = await createWorkflow(plainDef())
    const parent = await createWorkflow({
      schema_version: '2.0.0',
      triggers: [],
      nodes: [
        { id: 'a', type: 'sub_workflow', parameters: { workflow_id: child } },
        { id: 'b', type: 'sub_workflow', parameters: { workflow_id: child } },
      ],
      edges: [],
    })
    await publishOk(parent, 1)

    expect(await usedByCount(child)).toBe(1)
  })

  it('filters by trigger_node_ids (trigger-specific affected set)', async () => {
    const child = await createWorkflow(plainDef())
    const parentViaT1 = await createWorkflow(parentDef(child, 't1'))
    const parentViaT2 = await createWorkflow(parentDef(child, 't2'))
    await publishOk(parentViaT1, 1)
    await publishOk(parentViaT2, 1)

    expect(await usedByCount(child)).toBe(2) // no filter -> both
    expect(await usedByCount(child, ['t1'])).toBe(1) // only the T1 parent
    expect(await usedByCount(child, ['t1', 't2'])).toBe(2)
    expect(await usedByCount(child, ['t3'])).toBe(0)
  })

  it('returns zero for a workflow nothing references', async () => {
    const child = await createWorkflow(plainDef())
    expect(await usedByCount(child)).toBe(0)
    expect(await batchCount(child)).toBe(0)
  })
})

describe('Deletion confirmation (DELETE /workflows/{id})', () => {
  async function del(childId: string, confirm?: string): Promise<Response> {
    const query = confirm === undefined ? '' : `?confirm=${confirm}`
    return fetch(`${baseUrl}/api/v1/workflows/${childId}${query}`, { method: 'DELETE' })
  }

  it('returns a confirmation-required problem+json 409 and does not delete', async () => {
    const child = await createWorkflow(plainDef())
    const parent = await createWorkflow(parentDef(child))
    await publishOk(parent, 1)

    const res = await del(child)
    expect(res.status).toBe(409)
    expect(res.headers.get('content-type') ?? '').toContain('application/problem+json')
    const body: unknown = await res.json()
    if (!isRecord(body)) throw new Error('409 body was not an object')
    expect(body.code).toBe('WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED')
    expect(body.retryable).toBe(false)
    expect(body.referencing_count).toBe(1)

    // Not deleted: still retrievable.
    expect((await fetch(`${baseUrl}/api/v1/workflows/${child}`)).status).toBe(200)
  })

  it('treats confirm strictly: only the literal "true" bypasses the gate', async () => {
    const child = await createWorkflow(plainDef())
    const parent = await createWorkflow(parentDef(child))
    await publishOk(parent, 1)

    for (const value of ['false', '1', 'TRUE', 'yes', '']) {
      const res = await del(child, value)
      expect(res.status).toBe(409)
      await res.body?.cancel()
    }
    // Still present after every rejected attempt.
    expect((await fetch(`${baseUrl}/api/v1/workflows/${child}`)).status).toBe(200)

    const confirmed = await del(child, 'true')
    expect(confirmed.status).toBe(204)
    expect((await fetch(`${baseUrl}/api/v1/workflows/${child}`)).status).toBe(404)
  })

  it('deletes an unreferenced workflow without confirmation', async () => {
    const child = await createWorkflow(plainDef())
    const res = await del(child)
    expect(res.status).toBe(204)
    expect((await fetch(`${baseUrl}/api/v1/workflows/${child}`)).status).toBe(404)
  })
})

describe('Publication confirmation (removing a Subworkflow Trigger)', () => {
  /** Child whose v1 exposes a subworkflow_trigger with the given id. */
  function childWithTrigger(triggerId: string): Record<string, unknown> {
    return {
      schema_version: '2.0.0',
      triggers: [{ id: triggerId, type: 'subworkflow_trigger', parameters: {} }],
      nodes: [],
      edges: [],
    }
  }

  it('requires confirmation when a published parent invokes the removed trigger', async () => {
    const child = await createWorkflow(childWithTrigger('trig-a'))
    await publishOk(child, 1)
    const parent = await createWorkflow(parentDef(child, 'trig-a'))
    await publishOk(parent, 1)

    // New draft removes the trigger.
    await patchDefinition(child, { schema_version: '2.0.0', triggers: [], nodes: [], edges: [] })

    const blocked = await publish(child, 2)
    expect(blocked.status).toBe(409)
    expect(blocked.headers.get('content-type') ?? '').toContain('application/problem+json')
    const body: unknown = await blocked.json()
    if (!isRecord(body)) throw new Error('409 body was not an object')
    expect(body.code).toBe('WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED')
    expect(body.retryable).toBe(false)
    expect(body.affected_count).toBe(1)

    // Not published yet: v1 is still the published version.
    const detail: unknown = await (await fetch(`${baseUrl}/api/v1/workflows/${child}`)).json()
    if (!isRecord(detail)) throw new Error('detail not an object')
    expect(detail.published_version_number).toBe(1)

    // With confirm=true the publish goes through.
    const confirmed = await publish(child, 2, true)
    expect(confirmed.status).toBe(200)
  })

  it('does not gate when the removed trigger is not invoked by any published parent', async () => {
    const child = await createWorkflow(childWithTrigger('trig-x'))
    await publishOk(child, 1)
    // Parent references the child, but through a different trigger node.
    const parent = await createWorkflow(parentDef(child, 'some-other-trigger'))
    await publishOk(parent, 1)

    await patchDefinition(child, { schema_version: '2.0.0', triggers: [], nodes: [], edges: [] })

    const res = await publish(child, 2) // no confirm needed
    expect(res.status).toBe(200)
  })

  it('never gates the first publish, even when a parent already references the child', async () => {
    const child = await createWorkflow(childWithTrigger('trig-first'))
    const parent = await createWorkflow(parentDef(child, 'trig-first'))
    await publishOk(parent, 1)

    // First publish of the child: no previously-published version -> no gate.
    const res = await publish(child, 1)
    expect(res.status).toBe(200)
  })
})

describe('Contract fidelity of the confirmation 409 envelopes', () => {
  it('deletion 409 carries the full problem-details shape with a positive integer count', async () => {
    const child = await createWorkflow(plainDef())
    const parent = await createWorkflow(parentDef(child))
    await publishOk(parent, 1)

    const res = await fetch(`${baseUrl}/api/v1/workflows/${child}`, { method: 'DELETE' })
    expect(res.status).toBe(409)
    const body: unknown = await res.json()
    if (!isRecord(body)) throw new Error('409 body was not an object')
    expect(typeof body.type).toBe('string')
    expect(typeof body.title).toBe('string')
    expect(typeof body.detail).toBe('string')
    expect(typeof body.instance).toBe('string')
    expect(body.code).toBe('WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED')
    expect(body.retryable).toBe(false)
    expect(Number.isInteger(body.referencing_count)).toBe(true)
    expect(body.referencing_count as number).toBeGreaterThan(0)
    // The renamed count field is NOT present (would fail the `satisfies` binding on the mock).
    expect(body).not.toHaveProperty('affected_count')
  })

  it('generic 404 stays application/json (problem+json is specific to the confirmation 409s)', async () => {
    const res = await fetch(`${baseUrl}/api/v1/workflows/${uuidv4()}`, { method: 'DELETE' })
    expect(res.status).toBe(404)
    const ct = res.headers.get('content-type') ?? ''
    expect(ct).toContain('application/json')
    expect(ct).not.toContain('problem+json')
    await res.body?.cancel()
  })
})
