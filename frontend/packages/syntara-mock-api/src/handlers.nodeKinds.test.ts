import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'
import { disabledNodeKinds } from './resources/nodeKinds'

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

afterEach(() => {
  disabledNodeKinds.length = 0
})

type NodeKindRow = {
  kind: string
  category: string
  enabled: boolean
  switchable: boolean
  deniable_actions: string[]
  can_write: boolean
  attributes: { name: string; allowed_values: string[] | null }[]
}

const listNodeKinds = async (): Promise<{ resources: NodeKindRow[]; disabled_kinds: string[] }> =>
  fetch(`${baseUrl}/api/v1/node_kinds`).then((r) => r.json())

const setEnabled = (kind: string, enabled: boolean) =>
  fetch(`${baseUrl}/api/v1/node_kinds/${kind}/enabled`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })

describe('GET /api/v1/node_kinds', () => {
  it('lists every registered kind in backend declaration order', async () => {
    const body = await listNodeKinds()

    expect(body.resources[0].kind).toBe('manual_trigger')
    expect(body.resources.at(-1)?.kind).toBe('script')
    expect(body.resources.map((row) => row.kind)).toContain('mcp_tool')
  })

  it('reports deniable actions per category', async () => {
    const byKind = new Map((await listNodeKinds()).resources.map((row) => [row.kind, row]))

    expect(byKind.get('script')?.deniable_actions).toEqual(['write', 'execute'])
    expect(byKind.get('manual_trigger')?.deniable_actions).toEqual(['write'])
    expect(byKind.get('condition')?.deniable_actions).toEqual([])
  })

  it('reports policy attributes and their allowlists', async () => {
    const byKind = new Map((await listNodeKinds()).resources.map((row) => [row.kind, row]))

    expect(byKind.get('script')?.attributes).toEqual([{ name: 'language', allowed_values: ['python', 'bash'] }])
    expect(byKind.get('mcp_tool')?.attributes).toEqual([
      { name: 'tool_name', allowed_values: null },
      { name: 'integration_id', allowed_values: null },
    ])
    expect(byKind.get('manual_trigger')?.attributes).toEqual([])
  })

  it('marks flow control kinds as not switchable', async () => {
    const byKind = new Map((await listNodeKinds()).resources.map((row) => [row.kind, row]))

    expect(byKind.get('condition')?.switchable).toBe(false)
    expect(byKind.get('script')?.switchable).toBe(true)
  })

  it('starts with nothing switched off', async () => {
    const body = await listNodeKinds()

    expect(body.disabled_kinds).toEqual([])
    expect(body.resources.every((row) => row.enabled)).toBe(true)
  })
})

describe('PUT /api/v1/node_kinds/{kind}/enabled', () => {
  it('switches a kind off and echoes it in disabled_kinds', async () => {
    const response = await setEnabled('agentic', false)

    expect(response.status).toBe(200)
    expect(await response.json()).toMatchObject({ kind: 'agentic', enabled: false })

    const body = await listNodeKinds()
    expect(body.disabled_kinds).toEqual(['agentic'])
    expect(body.resources.find((row) => row.kind === 'agentic')?.enabled).toBe(false)
  })

  it('switches a kind back on', async () => {
    await setEnabled('agentic', false)
    const response = await setEnabled('agentic', true)

    expect(await response.json()).toMatchObject({ kind: 'agentic', enabled: true })
    expect((await listNodeKinds()).disabled_kinds).toEqual([])
  })

  it('returns 404 for an unknown kind', async () => {
    const response = await setEnabled('not_a_kind', false)

    expect(response.status).toBe(404)
  })

  it('returns 422 for a kind that cannot be switched off', async () => {
    expect((await setEnabled('condition', false)).status).toBe(422)
  })
})
