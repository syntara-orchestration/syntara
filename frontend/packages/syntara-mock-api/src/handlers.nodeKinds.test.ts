import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'
import { projectWriteDeniedNodeKinds, writeDeniedNodeKinds } from './resources/nodeKinds'

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

type StepTypePermission = {
  kind: string
  category: string
  can_write: boolean
  blocked_by: {
    kind: string
    label: string
    reason: string
    policy: string | null
    scope: string | null
    project: string | null
  } | null
}

const listNodeKinds = async (query: string): Promise<Response> => fetch(`${baseUrl}/api/v1/node_kinds?${query}`)

const FIRST_PROJECT_ID = 'p-001'
const SECOND_PROJECT_ID = 'p-002'

describe('GET /api/v1/node_kinds', () => {
  it('requires a project_id', async () => {
    const response = await fetch(`${baseUrl}/api/v1/node_kinds`)
    expect(response.status).toBe(422)
  })

  it('rejects an unknown project', async () => {
    const response = await listNodeKinds('project_id=00000000-0000-0000-0000-000000000000')
    expect(response.status).toBe(404)
  })

  it('serves every step type as writable by default', async () => {
    const response = await listNodeKinds(`project_id=${FIRST_PROJECT_ID}`)
    expect(response.status).toBe(200)
    const entries = (await response.json()) as StepTypePermission[]
    const byKind = new Map(entries.map((entry) => [entry.kind, entry]))
    expect(byKind.size).toBeGreaterThan(0)
    expect(byKind.get('script')).toMatchObject({ category: 'action', can_write: true, blocked_by: null })
    expect(byKind.get('condition')).toMatchObject({ category: 'flow_control', can_write: true })
    expect(byKind.get('manual_trigger')).toMatchObject({ category: 'trigger', can_write: true })
  })

  it('reports a global deny as blocked in every project', async () => {
    writeDeniedNodeKinds.push('script')
    try {
      for (const projectId of [FIRST_PROJECT_ID, SECOND_PROJECT_ID]) {
        const response = await listNodeKinds(`project_id=${projectId}`)
        const entries = (await response.json()) as StepTypePermission[]
        const script = entries.find((entry) => entry.kind === 'script')
        expect(script?.can_write).toBe(false)
        expect(script?.blocked_by).toMatchObject({ reason: 'explicit_deny', scope: 'any', project: null })
        expect(script?.blocked_by?.policy).toBeTruthy()
      }
    } finally {
      writeDeniedNodeKinds.length = 0
    }
  })

  it('reports a project deny as blocked only in that project', async () => {
    // p-001 is the 'default' project; p-002 is 'alice-sandbox'.
    projectWriteDeniedNodeKinds['default'] = ['script']
    try {
      const blocked = (await (await listNodeKinds(`project_id=${FIRST_PROJECT_ID}`)).json()) as StepTypePermission[]
      expect(blocked.find((entry) => entry.kind === 'script')?.blocked_by).toMatchObject({
        reason: 'explicit_deny',
        scope: 'project',
        project: 'default',
      })

      const elsewhere = (await (await listNodeKinds(`project_id=${SECOND_PROJECT_ID}`)).json()) as StepTypePermission[]
      expect(elsewhere.find((entry) => entry.kind === 'script')).toMatchObject({ can_write: true, blocked_by: null })
    } finally {
      delete projectWriteDeniedNodeKinds['default']
    }
  })
})
