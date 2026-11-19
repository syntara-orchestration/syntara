import { describe, expect, it } from 'vitest'

import { buildExpression } from '../../../../utils/expressions/templateBuilder'

import { buildSubWorkflowOutputSchemaTree, getDeclaredOutputFields } from './subWorkflowOutputSchema'

describe('getDeclaredOutputFields', () => {
  it('converts declared scalar properties and required names into picker fields', () => {
    const fields = getDeclaredOutputFields({
      type: 'object',
      properties: {
        status: { type: 'string' },
        retries: { type: 'integer' },
      },
      required: ['status'],
    })

    expect(fields).toEqual([
      { name: 'status', type: 'string', description: '', required: true },
      { name: 'retries', type: 'number', description: '', required: false },
    ])
  })

  it('returns null when the schema does not declare an object property map', () => {
    expect(getDeclaredOutputFields(null)).toBeNull()
    expect(getDeclaredOutputFields({ type: 'object', properties: [] })).toBeNull()
  })

  it('preserves nested declared output fields and required metadata', () => {
    const fields = getDeclaredOutputFields({
      type: 'object',
      properties: {
        intake: {
          type: 'object',
          properties: { status: { type: 'string', description: 'Intake status' } },
          required: ['status'],
        },
      },
      required: ['intake'],
    })

    expect(fields).toEqual([
      {
        name: 'intake',
        type: 'object',
        description: '',
        required: true,
        children: [{ name: 'status', type: 'string', description: 'Intake status', required: true }],
      },
    ])
  })
})

describe('buildSubWorkflowOutputSchemaTree', () => {
  it('builds a direct expression path from the declared output schema', () => {
    const childOutputFields = getDeclaredOutputFields({
      type: 'object',
      properties: { artifact_url: { type: 'string' } },
      required: ['artifact_url'],
    })
    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: '__declared_outputs__',
        name: 'Declared Outputs',
        type: 'subworkflow_declared_outputs',
        outputSchema: { type: 'object', properties: { artifact_url: { type: 'string' } } },
        outputFields: childOutputFields,
      },
    ])
    const outputs = tree.find((field) => field.name === 'outputs')
    const artifactUrl = outputs?.children?.find((field) => field.name === 'artifact_url')

    expect(artifactUrl).toBeDefined()
    expect(buildExpression({ nodeId: 'invoke_child', fieldPath: artifactUrl?.fieldPath ?? [] })).toBe(
      '${invoke_child.outputs.artifact_url}'
    )
  })

  it('builds direct expression paths for declared public field names', () => {
    const outputSchema = {
      type: 'object',
      properties: {
        status: { type: 'string' },
        image_tag: { type: 'string', description: 'Mapped by the child author' },
      },
    }
    const outputFields = getDeclaredOutputFields(outputSchema)
    expect(outputFields).not.toBeNull()

    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: '__declared_outputs__',
        name: 'Declared Outputs',
        type: 'subworkflow_declared_outputs',
        outputSchema,
        outputFields,
      },
    ])
    const outputs = tree.find((field) => field.name === 'outputs')
    const imageTag = outputs?.children?.find((field) => field.name === 'image_tag')

    expect(imageTag).toBeDefined()
    expect(buildExpression({ nodeId: 'invoke_child', fieldPath: imageTag?.fieldPath ?? [] })).toBe(
      '${invoke_child.outputs.image_tag}'
    )
    expect(outputs?.children?.some((field) => field.name === 'image_tag')).toBe(true)
  })

  it('builds nested expressions for declared output paths', () => {
    const outputFields = getDeclaredOutputFields({
      type: 'object',
      properties: {
        intake: { type: 'object', properties: { status: { type: 'string' } } },
      },
    })
    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: '__declared_outputs__',
        name: 'Declared Outputs',
        type: 'subworkflow_declared_outputs',
        outputSchema: { type: 'object' },
        outputFields,
      },
    ])
    const outputs = tree.find((field) => field.name === 'outputs')
    const intake = outputs?.children?.find((field) => field.name === 'intake')
    const status = intake?.children?.find((field) => field.name === 'status')

    expect(buildExpression({ nodeId: 'invoke_child', fieldPath: status?.fieldPath ?? [] })).toBe(
      '${invoke_child.outputs.intake.status}'
    )
  })

  it('does not expose internal child step outputs without a declared contract', () => {
    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: 'deploy_app',
        name: 'Deploy application',
        type: 'script',
        outputSchema: { type: 'object' },
        outputFields: [{ name: 'stdout', type: 'string', description: 'Internal step output' }],
      },
    ])
    const outputs = tree.find((field) => field.name === 'outputs')
    expect(outputs?.children).toBeUndefined()
  })
})
