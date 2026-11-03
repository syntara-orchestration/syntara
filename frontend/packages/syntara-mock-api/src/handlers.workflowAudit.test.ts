import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'

/**
 * Boots the mock API the same way `src/index.ts` does (http-middleware over the
 * MSW handlers) on an ephemeral port, so these assertions exercise the real
 * response bodies a consumer receives.
 */
let server: Server
let baseUrl: string

beforeAll(async () => {
  // createServer() returns an Express app; app.listen() is what yields the http.Server.
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

const isUserReference = (value: unknown): boolean =>
  typeof value === 'object' &&
  value !== null &&
  typeof (value as { id?: unknown }).id === 'string' &&
  typeof (value as { name?: unknown }).name === 'string'

describe('workflow audit fields are UserReference objects', () => {
  // Regression guard: WorkflowRead types updated_by as UserReference | null,
  // but the PATCH handler assigned the bare string 'user-1', so consumers lost
  // the id half and could not link the editor to a user page.
  it('returns updated_by as a UserReference after PATCH', async () => {
    const list = await fetch(`${baseUrl}/api/v1/workflows`).then((r) => r.json())
    const workflowId = list.resources[0].id

    const patched = await fetch(`${baseUrl}/api/v1/workflows/${workflowId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: 'audit shape check' }),
    }).then((r) => r.json())

    expect(isUserReference(patched.updated_by)).toBe(true)
  })

  it('returns every listed workflow version created_by as a UserReference', async () => {
    const list = await fetch(`${baseUrl}/api/v1/workflows`).then((r) => r.json())

    const bare = list.resources
      .filter((w: { version?: { created_by?: unknown } }) => w.version?.created_by != null)
      .filter((w: { version?: { created_by?: unknown } }) => !isUserReference(w.version?.created_by))
      .map((w: { name: string }) => w.name)

    expect(bare).toEqual([])
  })
})
