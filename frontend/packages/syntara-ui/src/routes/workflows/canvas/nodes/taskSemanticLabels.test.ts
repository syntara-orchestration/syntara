import { ExecutorTypeEnum, type TaskActivity } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { getTaskSemanticLabels } from './taskSemanticLabels'

function makeTask(
  overrides: Partial<TaskActivity> & Pick<TaskActivity, 'name' | 'type'> & { parameters: Record<string, unknown> }
): TaskActivity {
  return {
    id: 'a1',
    ...overrides,
  }
}

describe('getTaskSemanticLabels', () => {
  it('uses activity name and executor metadata label for script', () => {
    const data = makeTask({
      name: 'Run script',
      type: ExecutorTypeEnum.SCRIPT,
      parameters: { language: 'python', code: 'x' },
    })
    expect(getTaskSemanticLabels(data)).toEqual({
      title: 'Run script',
      typeLabel: 'Script',
    })
  })

  it('falls back to Untitled task when name missing', () => {
    const data = makeTask({
      name: '',
      type: ExecutorTypeEnum.HTTP_REQUEST,
      parameters: { method: 'GET', url: 'https://example.com' },
    })
    expect(getTaskSemanticLabels(data).title).toBe('Untitled task')
    expect(getTaskSemanticLabels(data).typeLabel).toBe('REST API')
  })

  it('falls back when name is whitespace-only', () => {
    const data = makeTask({
      name: '  \t',
      type: ExecutorTypeEnum.SCRIPT,
      parameters: { language: 'python', code: 'x' },
    })
    expect(getTaskSemanticLabels(data).title).toBe('Untitled task')
  })

  it('uses generic Task label for unknown executor key', () => {
    const data = {
      type: 'task',
      id: 'x',
      name: 'X',
      task: { executor: 'bogus', parameters: {} },
    } as unknown as TaskActivity
    expect(getTaskSemanticLabels(data).typeLabel).toBe('Task')
  })

  it('uses AAP Job when detectTaskNodeType resolves agentic+ansible connector to actualExecutor aap', () => {
    const data = makeTask({
      name: 'Run job',
      type: ExecutorTypeEnum.AGENTIC,
      parameters: {
        agent: 'default-agent',
        prompt: JSON.stringify({
          __type: 'connector',
          connectorId: 'ansible-automation-platform',
          operation: 'run-job',
          parameters: { jobId: '123' },
        }),
      },
    })
    expect(getTaskSemanticLabels(data)).toEqual({
      title: 'Run job',
      typeLabel: 'AAP Job',
    })
  })
})
