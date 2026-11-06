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
})

describe('buildSubWorkflowOutputSchemaTree', () => {
  it('builds an expression path from the current published output schema', () => {
    const childOutputFields = getNodeOutputSchema(ActivityTypeEnum.SCRIPT)
    expect(childOutputFields).not.toBeNull()

    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: 'deploy_app',
        name: 'Deploy application',
        type: ActivityTypeEnum.SCRIPT,
        outputSchema: { type: 'object' },
        outputFields: childOutputFields,
      },
    ])
    const result = tree.find((field) => field.name === 'Result')
    const outputs = result?.children?.find((field) => field.name === 'outputs')
    const childStep = outputs?.children?.find((field) => field.fieldPath.at(-1) === 'deploy_app')
    const childResult = childStep?.children?.find((field) => field.name === 'Result')
    const stdout = childResult?.children?.find((field) => field.name === 'stdout')

    expect(stdout).toBeDefined()
    expect(buildExpression({ nodeId: 'invoke_deploy', fieldPath: stdout?.fieldPath ?? [] })).toBe(
      '${invoke_deploy.Result.outputs.deploy_app.Result.stdout}'
    )
  })

  it('builds expression paths from mapped child output names', () => {
    const outputFields = getChildStepOutputFields('script', {
      type: 'object',
      properties: {
        status: { type: 'string' },
        image_tag: {
          description: 'Output produced by a configured mapping; its type is not statically known.',
          'x-syntara-output-mapped': true,
        },
      },
    })
    expect(outputFields).not.toBeNull()

    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: 'deploy_app',
        name: 'Deploy application',
        type: ActivityTypeEnum.SCRIPT,
        outputSchema: { type: 'object' },
        outputFields,
      },
    ])
    const result = tree.find((field) => field.name === 'Result')
    const outputs = result?.children?.find((field) => field.name === 'outputs')
    const childStep = outputs?.children?.find((field) => field.fieldPath.at(-1) === 'deploy_app')
    const childResult = childStep?.children?.find((field) => field.name === 'Result')
    const imageTag = childResult?.children?.find((field) => field.name === 'image_tag')

    expect(imageTag).toBeDefined()
    expect(buildExpression({ nodeId: 'invoke_deploy', fieldPath: imageTag?.fieldPath ?? [] })).toBe(
      '${invoke_deploy.Result.outputs.deploy_app.Result.image_tag}'
    )
    expect(childResult?.children?.some((field) => field.name === 'stdout')).toBe(false)
  })

  it('does not add another output envelope around a nested Sub-workflow step', () => {
    const nestedOutputFields = getNodeOutputSchema(ActivityTypeEnum.SUB_WORKFLOW)
    expect(nestedOutputFields).not.toBeNull()

    const tree = buildSubWorkflowOutputSchemaTree([
      {
        id: 'nested_call',
        name: 'Call nested workflow',
        type: ActivityTypeEnum.SUB_WORKFLOW,
        outputSchema: { type: 'object' },
        outputFields: nestedOutputFields,
      },
    ])
    const result = tree.find((field) => field.name === 'Result')
    const outputs = result?.children?.find((field) => field.name === 'outputs')
    const nestedStep = outputs?.children?.find((field) => field.fieldPath.at(-1) === 'nested_call')
    const nestedResult = nestedStep?.children?.find((field) => field.name === 'Result')
    const childExecutionId = nestedResult?.children?.find((field) => field.name === 'child_execution_id')
    const statusCode = nestedStep?.children?.find((field) => field.name === 'StatusCode')

    expect(buildExpression({ nodeId: 'invoke_parent', fieldPath: childExecutionId?.fieldPath ?? [] })).toBe(
      '${invoke_parent.Result.outputs.nested_call.Result.child_execution_id}'
    )
    expect(buildExpression({ nodeId: 'invoke_parent', fieldPath: statusCode?.fieldPath ?? [] })).toBe(
      '${invoke_parent.Result.outputs.nested_call.StatusCode}'
    )
  })
})
