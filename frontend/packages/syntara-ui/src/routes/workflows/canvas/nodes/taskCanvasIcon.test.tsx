import { ExecutorTypeEnum, type TaskActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { getTaskCanvasIcon } from './taskCanvasIcon'

function makeTask(
  overrides: Partial<TaskActivity> & Pick<TaskActivity, 'name' | 'type'> & { parameters: Record<string, unknown> }
): TaskActivity {
  return {
    id: 'task-1',
    ...overrides,
  }
}

describe('getTaskCanvasIcon', () => {
  it('renders an icon wrapper for a script task', () => {
    const data = makeTask({
      name: 'Run',
      type: ExecutorTypeEnum.SCRIPT,
      parameters: { language: 'python', code: 'print(1)' },
    })
    render(<>{getTaskCanvasIcon(data)}</>)
    expect(screen.getByTestId('step-icon-wrapper')).toBeInTheDocument()
  })

  it('applies accent color on canvas variant when provided', () => {
    const data = makeTask({
      name: 'Run',
      type: ExecutorTypeEnum.SCRIPT,
      parameters: { language: 'python', code: 'print(1)' },
    })
    render(<>{getTaskCanvasIcon(data, 'var(--pf-t--global--color--nonstatus--purple--300)')}</>)
    expect(screen.getByTestId('step-icon-wrapper')).toBeInTheDocument()
  })

  it('uses semanticZoom variant sizing when requested', () => {
    const data = makeTask({
      name: 'Run',
      type: ExecutorTypeEnum.SCRIPT,
      parameters: { language: 'python', code: 'print(1)' },
    })
    render(<>{getTaskCanvasIcon(data, 'var(--pf-t--global--color--nonstatus--purple--300)', 'semanticZoom')}</>)
    expect(screen.getByTestId('step-icon-wrapper')).toHaveClass('pf-m-3xl')
  })

  it('falls back to task type when executor metadata is missing', () => {
    const data = makeTask({
      name: 'HTTP',
      type: ExecutorTypeEnum.HTTP_REQUEST,
      parameters: { method: 'GET', url: 'https://example.com' },
    })
    render(<>{getTaskCanvasIcon(data)}</>)
    expect(screen.getByTestId('step-icon-wrapper')).toBeInTheDocument()
  })

  it('returns undefined when executor metadata has no icon', () => {
    const data = {
      type: 'task',
      id: 'x',
      name: 'X',
      task: { executor: 'bogus', parameters: {} },
    } as unknown as TaskActivity
    expect(getTaskCanvasIcon(data)).toBeUndefined()
  })
})
