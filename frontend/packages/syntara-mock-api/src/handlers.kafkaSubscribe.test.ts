import { createServer } from '@mswjs/http-middleware'
import type { FilteringAPI } from '@syntara/contracts'
import type { Server } from 'node:http'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { handlers } from './handlers'
import { createMockJwt } from './mockJwt'
import { workflows } from './resources/workflows'

let server: Server
let baseUrl: string
beforeAll(async () => {
  server = createServer(...handlers).listen(0)
  await new Promise<void>((resolve, reject) => {
    server.once('listening', resolve)
    server.once('error', reject)
  })
  const address = server.address()
  if (!address || typeof address === 'string') throw new Error('Mock server did not bind')
  baseUrl = `http://127.0.0.1:${address.port}`
})
afterAll(async () => {
  if (server?.listening)
    await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())))
})
const workflow = workflows.find((item) => item.project_id === 'p-001')
const body = {
  integration_id: '11111111-1111-4111-8111-111111111111',
  credential_id: '22222222-2222-4222-8222-222222222222',
  topic: 'orders',
}

function preflight(username: string, parameters: object = body) {
  return fetch(`${baseUrl}/api/v1/workflows/${workflow?.id}/event_subscriptions/test`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${createMockJwt({ username, userId: username })}`,
    },
    body: JSON.stringify(parameters),
  })
}

describe('Kafka subscription preflight mock', () => {
  it.each(['admin', 'user'])(
    'permits %s to check a valid binding without claiming READ/group permissions',
    async (username) => {
      expect(workflow).toBeDefined()
      const response = await preflight(username)
      expect(response.status).toBe(200)
      expect(await response.json()).toMatchObject({
        success: true,
        connection: 'verified',
        topic_metadata: 'verified',
        topic_read: 'unverified',
        group_access: 'unverified',
      })
    }
  )

  it.each(['viewer', 'auditor'])('denies %s', async (username) => {
    expect((await preflight(username)).status).toBe(403)
  })

  it.each([
    { ...body, topic: 'orders.*' },
    { ...body, credential_id: '' },
    { ...body, integration_id: 'other' },
  ])('rejects invalid bindings', async (parameters) => {
    expect((await preflight('admin', parameters)).status).toBe(422)
  })
})

describe('Kafka filter test mock', () => {
  function testFilter(body: FilteringAPI.components['schemas']['FilterTestRequest']) {
    return fetch(`${baseUrl}/api/v1/filtering/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  }

  it.each([
    ['true', 'match'],
    ['false', 'no_match'],
    ['input.missing', 'evaluation_error'],
    ['constructor', 'evaluation_error'],
    ['', 'match'],
    ['  \n', 'match'],
    [null, 'match'],
    [undefined, 'match'],
  ] as const)('returns the contracted outcome for fixture %s', async (expression, outcome) => {
    const response = await testFilter({ expression, input: null })
    expect(response.status).toBe(200)
    expect(await response.json()).toStrictEqual(
      outcome === 'evaluation_error' ? { outcome, error_code: 'filter_evaluation_failed' } : { outcome }
    )
  })

  it('returns safe configuration errors with compiler locations', async () => {
    const response = await testFilter({ expression: 'input.', input: { private: 'sample data' } })
    expect(response.status).toBe(422)
    expect(await response.json()).toStrictEqual({
      type: 'https://api.example.com/errors/validation-error',
      title: 'Invalid CEL filter expression',
      detail: 'filter_invalid_syntax',
      code: 'filter_invalid_syntax',
      retryable: false,
      line: 1,
      column: 7,
    })
  })
})
