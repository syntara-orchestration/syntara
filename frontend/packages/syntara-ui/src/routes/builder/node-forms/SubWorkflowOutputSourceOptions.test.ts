import { ActivityTypeEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { getStepOutputChoices, isDynamicOutputExpression } from './SubWorkflowOutputSourceOptions'

describe('getStepOutputChoices', () => {
  it('returns nested outputs only from steps reachable from the selected trigger', () => {
    const choices = getStepOutputChoices(
      [
        {
          id: 'deploy',
          name: 'Deploy',
          type: ActivityTypeEnum.SCRIPT,
          output_schema: [
            {
              name: 'release',
              type: 'object',
              description: 'Release metadata',
              children: [{ name: 'tag', type: 'string', description: 'Release tag' }],
            },
          ],
        },
        {
          id: 'other-branch',
          name: 'Other branch',
          type: ActivityTypeEnum.SCRIPT,
          output_schema: [{ name: 'ignored', type: 'string', description: 'Not reachable' }],
        },
      ],
      [
        { source: 'trigger-incident', target: 'deploy' },
        { source: 'trigger-change', target: 'other-branch' },
      ],
      'trigger-incident',
      0
    )

    expect(choices.map(({ expression, fieldName, stepName }) => ({ expression, fieldName, stepName }))).toEqual([
      { expression: '${deploy.release}', fieldName: 'release', stepName: 'Deploy' },
      { expression: '${deploy.release.tag}', fieldName: 'release.tag', stepName: 'Deploy' },
    ])
    expect(choices[0]?.allowsDynamicDescendants).toBe(false)
  })

  it('uses a trigger-index fallback and the node output schema when no declared fields are usable', () => {
    const choices = getStepOutputChoices(
      [
        { id: 'script-step', type: ActivityTypeEnum.SCRIPT, output_schema: [{ name: 3 }] },
        { id: 'unnamed-step', type: ActivityTypeEnum.SCRIPT, name: '', output_schema: [] },
      ],
      [
        { source: 'trigger-4', target: 'script-step' },
        { source: 'trigger-4', target: 'unnamed-step' },
      ],
      'unmatched-trigger',
      4
    )

    expect(choices.some((choice) => choice.expression === '${script-step.stdout}')).toBe(true)
    expect(choices.every((choice) => choice.stepName === 'script-step' || choice.stepName === 'unnamed-step')).toBe(
      true
    )
    expect(choices.every((choice) => choice.sourceDescription.length > 0)).toBe(true)
  })

  it('preserves generated output metadata for existing node types in the picker', () => {
    const choices = getStepOutputChoices(
      [
        { id: 'request', name: 'Request', type: ActivityTypeEnum.HTTP_REQUEST },
        { id: 'agent', name: 'Agent', type: ActivityTypeEnum.AGENTIC },
        { id: 'loop', name: 'Loop', type: ActivityTypeEnum.LOOP },
      ],
      [
        { source: 'trigger-0', target: 'request' },
        { source: 'trigger-0', target: 'agent' },
        { source: 'trigger-0', target: 'loop' },
      ],
      'trigger-0',
      0
    )

    const requestHeaders = choices.find((choice) => choice.expression === '${request.headers}')
    expect(requestHeaders).toMatchObject({ type: 'object', allowsDynamicDescendants: true })
    expect(isDynamicOutputExpression('${request.headers.content_type}', choices)).toBe(true)

    expect(
      choices.find((choice) => choice.expression === '${agent.structured_output_metadata.fallback_strategy_used}')
    ).toMatchObject({ type: 'string', allowsDynamicDescendants: false })
    expect(choices.find((choice) => choice.expression === '${agent.integration_ids}')).toMatchObject({
      type: 'array',
      allowsDynamicDescendants: false,
    })

    const loopResults = choices.find((choice) => choice.expression === '${loop.iteration_results}')
    expect(loopResults).toMatchObject({ type: 'object', allowsDynamicDescendants: true })
    expect(isDynamicOutputExpression('${loop.iteration_results.task.stdout}', choices)).toBe(true)
  })
})

describe('isDynamicOutputExpression', () => {
  it('accepts descendants of unknown or open object outputs', () => {
    const choices = [
      {
        expression: '${step.payload}',
        fieldName: 'payload',
        stepName: 'Step',
        type: 'unknown' as const,
        sourceDescription: 'Dynamic payload',
        allowsDynamicDescendants: true,
      },
      {
        expression: '${step.metadata}',
        fieldName: 'metadata',
        stepName: 'Step',
        type: 'object' as const,
        sourceDescription: 'Open metadata',
        allowsDynamicDescendants: true,
      },
    ]

    expect(isDynamicOutputExpression('${step.payload.revision.tag}', choices)).toBe(true)
    expect(isDynamicOutputExpression(' ${step.metadata.owner} ', choices)).toBe(true)
  })

  it('rejects malformed expressions, shallow paths, and descendants of closed fields', () => {
    const choices = [
      {
        expression: '${step.name}',
        fieldName: 'name',
        stepName: 'Step',
        type: 'string' as const,
        sourceDescription: 'Name',
        allowsDynamicDescendants: false,
      },
    ]

    expect(isDynamicOutputExpression('${step.name}', choices)).toBe(false)
    expect(isDynamicOutputExpression('${step.name.first}', choices)).toBe(false)
    expect(isDynamicOutputExpression('step.name.first', choices)).toBe(false)
    expect(isDynamicOutputExpression('${step..first}', choices)).toBe(false)
  })
})
