import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { NodeSemanticZoomBody } from './NodeSemanticZoomBody'

describe('NodeSemanticZoomBody', () => {
  it('exposes name and type in aria-label', () => {
    render(
      <NodeSemanticZoomBody
        title="Analyze Data"
        typeLabel="Task Agent"
        backgroundColor="rgb(100, 100, 200)"
        selected={false}
        hasDashedBorder={false}
      />
    )

    expect(screen.getByRole('button', { name: 'Analyze Data, Task Agent' })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <NodeSemanticZoomBody
        title="Node A"
        typeLabel="Condition"
        backgroundColor="#ccc"
        selected={false}
        hasDashedBorder={false}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows tooltip content on hover', async () => {
    const user = userEvent.setup()
    render(
      <NodeSemanticZoomBody
        title="My Task"
        typeLabel="REST API"
        backgroundColor="#999"
        selected={false}
        hasDashedBorder={false}
      />
    )

    await user.hover(screen.getByRole('button', { name: 'My Task, REST API' }))

    expect(await screen.findByText('My Task')).toBeInTheDocument()
    expect(screen.getByText('REST API')).toBeInTheDocument()
  })
})
