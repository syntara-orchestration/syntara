import { createServer } from '@mswjs/http-middleware'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'

type MockApiServer = {
  address: () => { port: number } | string | null
  close: (callback: (error?: Error) => void) => void
  once(event: 'listening', listener: () => void): void
  once(event: 'error', listener: (error: Error) => void): void
}

let server: MockApiServer
let baseUrl: string

beforeAll(async () => {
  const createMockServer = createServer as unknown as (...mockHandlers: unknown[]) => {
    listen: (port: number, hostname: string) => MockApiServer
  }
  const app = createMockServer(...handlers)
  server = app.listen(0, '127.0.0.1')
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

describe('retry from failure mock handler', () => {
  it('replays completed outputs without carrying the failed retry point into the new execution', async () => {
    const retryResponse = await fetch(`${baseUrl}/api/v1/executions/exec-retry-demo/retry_from_failure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ retry_point_ids: ['step2'] }),
    })
    expect(retryResponse.status).toBe(201)
    const retriedExecution = (await retryResponse.json()) as { id: string }

    const activityResponse = await fetch(`${baseUrl}/api/v1/executions/${retriedExecution.id}/activities`)
    const { resources } = (await activityResponse.json()) as {
      resources: Array<{ activity_name: string; execution_id: string; status: string }>
    }

    expect(resources).toHaveLength(1)
    expect(resources[0]).toMatchObject({
      activity_name: 'step1',
      execution_id: retriedExecution.id,
      status: 'completed',
    })
  })
})
