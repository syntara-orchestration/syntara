import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { ExecutionTargetStatusLabel } from './ExecutionTargetStatusLabel'

describe('ExecutionTargetStatusLabel', () => {
  it('renders capitalized status', () => {
    render(<ExecutionTargetStatusLabel status="provisioning" />)
    expect(screen.getByText('Provisioning')).toBeInTheDocument()
  })

  it('normalizes uppercase status for visual lookup', () => {
    render(<ExecutionTargetStatusLabel status="READY" />)
    expect(screen.getByText('READY')).toBeInTheDocument()
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
    render(<ExecutionTargetStatusLabel status="error" message="Node not ready" />)
    await user.hover(screen.getByText('Error'))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Node not ready')
  })

  it('does not show a tooltip when message is null', () => {
    render(<ExecutionTargetStatusLabel status="ready" message={null} />)
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExecutionTargetStatusLabel status="ready" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
