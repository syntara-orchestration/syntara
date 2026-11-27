import { ActivityTypeEnum, type WorkflowAPI } from '@syntara/contracts'
import { z } from 'zod'

import type { Page } from '../fixtures'

const definitionSchema = z.looseObject({
  nodes: z.array(z.looseObject({ id: z.string(), type: z.string(), parameters: z.record(z.string(), z.unknown()) })),
})

function validationFor(
  definition: z.infer<typeof definitionSchema>
): WorkflowAPI.components['schemas']['ValidationResult'] {
  const findings: WorkflowAPI.components['schemas']['ValidationFinding'][] = []
  for (const node of definition.nodes.filter((node) => node.type === ActivityTypeEnum.KAFKA_PUBLISH)) {
    for (const field of ['integration_id', 'credential_id', 'topic', 'payload']) {
      if (node.parameters[field] !== undefined && node.parameters[field] !== '') continue
      findings.push({
        severity: 'error',
        category: 'missing_field',
        node_id: node.id,
        field_path: `parameters.${field}`,
        message: field === 'payload' ? 'JSON payload is required' : `${field} is required`,
      })
    }
  }
  return { is_valid: findings.length === 0, error_count: findings.length, warning_count: 0, findings }
}

export async function mockKafkaAdvisorySaves(
  app: Page,
  { workflowId, omitCreatedVersion }: { workflowId?: string; omitCreatedVersion?: boolean } = {}
) {
  // Keep the real mock API's persistence; supply the production advisory validation contract.
  await app.route(
    (url) => {
      const path = url.pathname
      return (
        path === '/api/v1/workflows/validate' ||
        (workflowId ? path === `/api/v1/workflows/${workflowId}` : /^\/api\/v1\/workflows(?:\/[^/]+)?$/.test(path))
      )
    },
    async (route) => {
      const request = route.request()
      const method = request.method()
      const path = new URL(request.url()).pathname
      if (path.endsWith('/validate')) {
        const body: unknown = request.postDataJSON()
        const { workflow_definition: definition } = z.object({ workflow_definition: definitionSchema }).parse(body)
        await route.fulfill({ json: validationFor(definition) })
        return
      }
      if (method === 'GET' && path === '/api/v1/workflows') return route.fallback()
      if (!['GET', 'POST', 'PATCH'].includes(method)) return route.fallback()
      const response = await route.fetch()
      if (!response.ok()) return route.fulfill({ response })
      const body: unknown = await response.json()
      const data = z
        .looseObject({
          version: z.looseObject({ workflow_definition: definitionSchema }).optional(),
        })
        .parse(body)
      const isSave = method === 'POST' || method === 'PATCH'
      const requestBody: unknown = isSave ? request.postDataJSON() : undefined
      const definition = isSave
        ? z.object({ workflow_definition: definitionSchema.optional() }).parse(requestBody).workflow_definition
        : data.version?.workflow_definition
      if (!definition) return route.fulfill({ response })
      const validation = validationFor(definition)
      const json = {
        ...data,
        has_validation_issues: !validation.is_valid,
        ...(isSave && { validation_result: validation }),
      }
      // Production create responses omit the version; the builder must load it after navigating.
      if (method === 'POST' && omitCreatedVersion) delete json.version
      await route.fulfill({ response, json })
    }
  )
}
