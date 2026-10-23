import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ExecutionTargetStatusLabel } from './ExecutionTargetStatusLabel'

describe('ExecutionTargetStatusLabel', () => {
  it('renders capitalized EP status', () => {
    render(<ExecutionTargetStatusLabel status="bootstrapping" />)
    expect(screen.getByText('Bootstrapping')).toBeInTheDocument()
  })

  it('normalizes uppercase status for visual lookup', () => {
    render(<ExecutionTargetStatusLabel status="ACTIVE" />)
    expect(screen.getByText('ACTIVE')).toBeInTheDocument()
  })

  it('replaces underscores in status labels', () => {
    render(<ExecutionTargetStatusLabel status="node_not_ready" />)
    expect(screen.getByText('Node not ready')).toBeInTheDocument()
  })

  it('falls back to a custom visual for unknown statuses', () => {
    render(<ExecutionTargetStatusLabel status="mystery" />)
    expect(screen.getByText('Mystery')).toBeInTheDocument()
  })

  it('shows tooltip for status message', async () => {
    const user = userEvent.setup()
    render(<ExecutionTargetStatusLabel status="failed" message="Node not ready" />)
    await user.hover(screen.getByText('Failed'))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Node not ready')
  })

  it('does not show a tooltip when message is null', () => {
    render(<ExecutionTargetStatusLabel status="active" message={null} />)
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExecutionTargetStatusLabel status="active" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
