import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'

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

type GroupRow = { created_by: { id: string; name: string } | null }

const listGroups = async (query: string): Promise<GroupRow[]> => {
  const body = await fetch(`${baseUrl}/api/v1/groups?${query}`).then((r) => r.json())
  return body.resources as GroupRow[]
}

describe('groups created_by_name[contains] filter', () => {
  // Production (group_service.handle_created_by_name) matches User.username, while
  // UserReference.name is the display name. The seeded user 'demo' has the display
  // name 'Demo Admin', so a username term must match and a display-name-only term must not.
  it('matches on the creator username, like the backend', async () => {
    const byUsername = await listGroups('created_by_name[contains]=demo')
    expect(byUsername.length).toBeGreaterThan(0)
    expect(byUsername.every((g) => g.created_by?.id === 'a1b2c3d4-e5f6-7890-abcd-ef1234567890')).toBe(true)
  })

  it('does not match on the display name alone', async () => {
    const byDisplayName = await listGroups('created_by_name[contains]=Admin')
    expect(byDisplayName).toHaveLength(0)
  })
})
