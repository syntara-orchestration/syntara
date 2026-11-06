import { ActivityTypeEnum, getNodeOutputSchema } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { buildExpression } from '../../../../utils/expressions/templateBuilder'

import { buildSubWorkflowOutputSchemaTree } from './subWorkflowOutputSchema'

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
})
