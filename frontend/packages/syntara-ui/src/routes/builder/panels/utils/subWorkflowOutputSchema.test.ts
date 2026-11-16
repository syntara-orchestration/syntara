import { ActivityTypeEnum, getNodeOutputSchema } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { buildExpression } from '../../../../utils/expressions/templateBuilder'

import { buildSubWorkflowOutputSchemaTree, getChildStepOutputFields } from './subWorkflowOutputSchema'

describe('getChildStepOutputFields', () => {
  it('keeps the generated step schema when outputs are not remapped', () => {
    const fields = getChildStepOutputFields('script', {
      type: 'object',
      properties: {
        status: { type: 'string' },
        stdout: { type: 'string' },
      },
    })

    expect(fields?.map((field) => field.name)).toEqual(['status', 'stdout'])
    expect(fields?.find((field) => field.name === 'stdout')?.description).toBe('Standard output from script execution')
  })

  it('uses mapped output names and marks mapped field types as unknown', () => {
    const fields = getChildStepOutputFields('script', {
      type: 'object',
      properties: {
        status: { type: 'string' },
        stdout: {
          description: 'Output produced by a configured mapping; its type is not statically known.',
          'x-syntara-output-mapped': true,
        },
        image_tag: {
          description: 'Output produced by a configured mapping; its type is not statically known.',
          'x-syntara-output-mapped': true,
        },
      },
    })

    expect(fields?.map((field) => field.name)).toEqual(['status', 'stdout', 'image_tag'])
    expect(fields?.find((field) => field.name === 'stdout')?.type).toBe('unknown')
    expect(fields?.some((field) => field.name === 'stderr')).toBe(false)
  })

  it('suppresses mapped fields when the effective schema contains no mappings', () => {
    const fields = getChildStepOutputFields('script', {
      type: 'object',
      properties: { status: { type: 'string' } },
    })

    expect(fields?.map((field) => field.name)).toEqual(['status'])
  })

  it('preserves nested declared output fields and required metadata', () => {
    const fields = getChildStepOutputFields('subworkflow_declared_outputs', {
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
    const childOutputFields = getChildStepOutputFields('subworkflow_declared_outputs', {
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
    const result = tree.find((field) => field.name === 'Result')
    const outputs = result?.children?.find((field) => field.name === 'outputs')
    const artifactUrl = outputs?.children?.find((field) => field.name === 'artifact_url')

    expect(artifactUrl).toBeDefined()
    expect(buildExpression({ nodeId: 'invoke_child', fieldPath: artifactUrl?.fieldPath ?? [] })).toBe(
      '${invoke_child.Result.outputs.artifact_url}'
    )
  })

  it('builds direct expression paths from mapped public output names', () => {
    const outputSchema = {
      type: 'object',
      properties: {
        status: { type: 'string' },
        stdout: {
          description: 'Output produced by a configured mapping; its type is not statically known.',
          'x-syntara-output-mapped': true,
        },
        image_tag: {
          description: 'Output produced by a configured mapping; its type is not statically known.',
          'x-syntara-output-mapped': true,
        },
      },
    }
    const outputFields = getChildStepOutputFields('subworkflow_declared_outputs', outputSchema)
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
    const result = tree.find((field) => field.name === 'Result')
    const outputs = result?.children?.find((field) => field.name === 'outputs')
    const imageTag = outputs?.children?.find((field) => field.name === 'image_tag')

    expect(imageTag).toBeDefined()
    expect(buildExpression({ nodeId: 'invoke_deploy', fieldPath: imageTag?.fieldPath ?? [] })).toBe(
      '${invoke_deploy.Result.outputs.image_tag}'
    )
    expect(outputs?.children?.some((field) => field.name === 'stdout')).toBe(true)
  })

  it('builds nested expressions for declared output paths', () => {
    const outputFields = getChildStepOutputFields('subworkflow_declared_outputs', {
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
    const result = tree.find((field) => field.name === 'Result')
    const outputs = result?.children?.find((field) => field.name === 'outputs')
    const intake = outputs?.children?.find((field) => field.name === 'intake')
    const status = intake?.children?.find((field) => field.name === 'status')

    expect(buildExpression({ nodeId: 'invoke_child', fieldPath: status?.fieldPath ?? [] })).toBe(
      '${invoke_child.Result.outputs.intake.status}'
    )
  })

  it('does not expose internal child step outputs without a declared contract', () => {
    const internalOutputFields = getNodeOutputSchema(ActivityTypeEnum.SCRIPT)
    expect(internalOutputFields).not.toBeNull()
    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: 'deploy_app',
        name: 'Deploy application',
        type: ActivityTypeEnum.SCRIPT,
        outputSchema: { type: 'object' },
        outputFields: internalOutputFields,
      },
    ])
    const result = tree.find((field) => field.name === 'Result')
    const outputs = result?.children?.find((field) => field.name === 'outputs')
    expect(outputs?.children).toBeUndefined()
  })
})
