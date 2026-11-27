import { createServer } from '@mswjs/http-middleware'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'

type MockServer = ReturnType<ReturnType<typeof createServer>['listen']>
let server: MockServer
let credentialsUrl: string

beforeAll(async () => {
  // The middleware types still expect MSW 2 handlers. The mock API runs MSW 3.
  const middlewareHandlers = handlers as unknown as Parameters<typeof createServer>
  server = createServer(...middlewareHandlers).listen(0)
  await new Promise<void>((resolve, reject) => {
    server.once('listening', resolve)
    server.once('error', reject)
  })
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Mock server did not bind')
  credentialsUrl = `http://127.0.0.1:${address.port}/api/v1/credentials`
})

afterAll(async () => {
  if (server?.listening) {
    await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())))
  }
})

describe('mTLS credential responses', () => {
  it('keeps a cleared passphrase absent after saving and refetching the identity', async () => {
    const certificate = 'mock certificate'
    const headers = { 'Content-Type': 'application/json' }
    const created = await fetch(credentialsUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        name: 'Mock identity for passphrase clear test',
        credential_type_id: 'ctype-mtls-client-identity',
        project_id: 'p-001',
        inputs: {
          client_certificate: certificate,
          client_private_key: 'mock protected key',
          client_key_passphrase: 'mock passphrase',
        },
      }),
    })
    expect(created.status).toBe(201)
    const credential = (await created.json()) as { id: string; inputs: Record<string, unknown> }
    const url = `${credentialsUrl}/${credential.id}`
    const expectedInputs = { client_certificate: certificate, client_private_key: '$encrypted$' }

    try {
      expect(credential.inputs).toEqual({ ...expectedInputs, client_key_passphrase: '$encrypted$' })

      const updated = await fetch(url, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ inputs: { client_private_key: 'mock unprotected key', client_key_passphrase: null } }),
      })

      expect(updated.status).toBe(200)
      expect(await updated.json()).toHaveProperty('inputs', expectedInputs)
      const fetched = await fetch(url)
      expect(fetched.status).toBe(200)
      expect(await fetched.json()).toHaveProperty('inputs', expectedInputs)
    } finally {
      await fetch(url, { method: 'DELETE' })
    }
  })
})
