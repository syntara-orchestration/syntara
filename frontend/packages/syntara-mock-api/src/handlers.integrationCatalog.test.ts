import { createServer } from '@mswjs/http-middleware'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'
import { integrations } from './resources/integrations'

type MockServer = ReturnType<ReturnType<typeof createServer>['listen']>
let server: MockServer
let baseUrl: string
beforeAll(async () => {
  // The middleware still declares MSW 2 handlers; the running mock API uses MSW 3.
  const middlewareHandlers = handlers as unknown as Parameters<typeof createServer>
  server = createServer(...middlewareHandlers).listen(0)
  await new Promise<void>((resolve, reject) => {
    server.once('listening', resolve)
    server.once('error', reject)
  })
  const address = server.address()
  if (address === null || typeof address === 'string') throw new Error('Mock API did not bind a TCP port')
  baseUrl = `http://127.0.0.1:${address.port}`
})
afterAll(async () => {
  await new Promise<void>((resolve, reject) => server.close((error?: Error) => (error ? reject(error) : resolve())))
})

async function readList(path: string): Promise<unknown> {
  const response = await fetch(`${baseUrl}/api/v1/${path}`)
  expect(response.status).toBe(200)
  const data: unknown = await response.json()
  return data
}

describe('integration catalog', () => {
  it('includes Kafka and legacy rows in one sorted list with a combined total', async () => {
    const expected = [...integrations].sort((a, b) => a.name.localeCompare(b.name))
    expect(await readList('integrations/catalog?sort=name&include_total=true&limit=100')).toMatchObject({
      total: expected.length,
      resources: expected.map(({ id, name }) => ({ id, name })),
    })
  })

  it('filters the catalog to Kafka while preserving the Kafka configuration contract', async () => {
    const expected = integrations.filter((item) => item.integration_type === 'kafka')
    expect(await readList('integrations/catalog?integration_type=kafka&include_total=true&limit=100')).toMatchObject({
      total: expected.length,
      resources: expected.map(({ id }) => ({
        id,
        integration_type: 'kafka',
        configuration: { bootstrap_servers: expect.any(Array) },
      })),
    })
  })

  it('continues to exclude Kafka from the original integrations endpoint', async () => {
    const expected = integrations.filter((item) => item.integration_type !== 'kafka')
    expect(await readList('integrations?include_total=true&limit=100')).toMatchObject({
      total: expected.length,
      resources: expected.map(({ id }) => ({ id })),
    })
  })
})
