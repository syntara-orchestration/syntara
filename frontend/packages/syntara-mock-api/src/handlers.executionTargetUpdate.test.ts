import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'
import { DEFAULT_EXECUTION_TARGET_ID, UPDATE_CONFLICT_TARGET_ID } from './resources/executionTargets'

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

async function patchTarget(targetId: string, body: Record<string, unknown>): Promise<Response> {
  return fetch(`${baseUrl}/api/execution_plane/v1/execution_targets/${targetId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

describe('PATCH /api/execution_plane/v1/execution_targets/:target_id', () => {
  it('applies a partial name update', async () => {
    const stagingId = 'a1000000-0000-4000-8000-000000000002'
    const response = await patchTarget(stagingId, { name: 'Staging OpenShift Renamed' })
    expect(response.status).toBe(200)
    const body = (await response.json()) as { id: string; name: string }
    expect(body).toMatchObject({ id: stagingId, name: 'Staging OpenShift Renamed' })
  })

  it('returns field-level 422 when name is cleared', async () => {
    const response = await patchTarget(DEFAULT_EXECUTION_TARGET_ID, { name: '   ' })
    expect(response.status).toBe(422)
    const body = (await response.json()) as { detail: Array<{ loc: unknown[]; msg: string }> }
    expect(body.detail[0]?.loc).toEqual(['body', 'name'])
    expect(body.detail[0]?.msg).toMatch(/cannot be empty/i)
  })

  it('returns field-level 422 when placement.namespace is missing', async () => {
    const response = await patchTarget(DEFAULT_EXECUTION_TARGET_ID, {
      placement: { type: 'kubernetes', node_selectors: ['region=us-west'] },
    })
    expect(response.status).toBe(422)
    const body = (await response.json()) as { detail: Array<{ loc: unknown[] }> }
    expect(body.detail[0]?.loc).toEqual(['body', 'placement', 'namespace'])
  })

  it('returns 409 for a concurrent-edit conflict target', async () => {
    const response = await patchTarget(UPDATE_CONFLICT_TARGET_ID, { name: 'Should Not Apply' })
    expect(response.status).toBe(409)
    const body = (await response.json()) as { code: string; detail: string }
    expect(body.code).toBe('CONFLICT')
    expect(body.detail).toMatch(/modified by another user/i)
  })

  it('returns 409 when renaming to an existing target name', async () => {
    const response = await patchTarget(DEFAULT_EXECUTION_TARGET_ID, { name: 'Worker Pool 03' })
    expect(response.status).toBe(409)
    const body = (await response.json()) as { code: string }
    expect(body.code).toBe('CONFLICT')
  })
})
