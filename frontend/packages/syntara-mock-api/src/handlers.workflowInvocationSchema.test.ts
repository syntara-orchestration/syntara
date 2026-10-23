import { createServer } from '@mswjs/http-middleware'
import type { Server } from 'http'
import { v4 as uuidv4 } from 'uuid'
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

describe('workflow invocation schema mock', () => {
  it('returns Subworkflow Trigger schemas from the published version', async () => {
    const workflowName = `invocation-schema-${uuidv4()}`
    const createResponse = await fetch(`${baseUrl}/api/v1/workflows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: workflowName,
        project_id: 'p-001',
        workflow_definition: {
          schema_version: '2.0.0',
          name: workflowName,
          triggers: [
            { id: 'manual_entry', type: 'manual_trigger', parameters: {} },
            {
              id: 'child_entry',
              name: 'Child Entry',
              type: 'subworkflow_trigger',
              parameters: {
                input_schema: {
                  type: 'object',
                  properties: { username: { type: 'string' } },
                  required: ['username'],
                },
              },
            },
            { id: 'child_entry_secondary', type: 'subworkflow_trigger', parameters: {} },
          ],
          nodes: [],
          edges: [],
        },
      }),
    })
    expect(createResponse.status).toBe(201)

    const createdWorkflow: unknown = await createResponse.json()
    if (!isRecord(createdWorkflow) || typeof createdWorkflow.id !== 'string') {
      throw new Error('workflow creation response did not include an id')
    }
    const workflowId = createdWorkflow.id
    const invocationSchemaUrl = `${baseUrl}/api/v1/workflows/${workflowId}/invocation_schema`

    const unpublishedResponse = await fetch(invocationSchemaUrl)
    expect(unpublishedResponse.status).toBe(404)

    const publishResponse = await fetch(`${baseUrl}/api/v1/workflows/${workflowId}/versions/1/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_version: 1 }),
    })
    expect(publishResponse.status).toBe(200)

    const response = await fetch(invocationSchemaUrl)
    expect(response.status).toBe(200)
    const result: unknown = await response.json()
    expect(result).toEqual({
      workflow_id: workflowId,
      published_version_id: expect.any(String),
      published_version: 1,
      is_eligible: true,
      triggers: [
        {
          trigger_node_id: 'child_entry',
          name: 'Child Entry',
          input_schema: {
            type: 'object',
            properties: { username: { type: 'string' } },
            required: ['username'],
          },
        },
        { trigger_node_id: 'child_entry_secondary', name: null, input_schema: {} },
      ],
    })
  })
})
