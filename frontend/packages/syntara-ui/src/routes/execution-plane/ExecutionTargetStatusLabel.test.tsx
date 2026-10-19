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

  it('shows tooltip for status message', async () => {
    const user = userEvent.setup()
    render(<ExecutionTargetStatusLabel status="error" message="Node not ready" />)
    await user.hover(screen.getByText('Error'))
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Node not ready')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExecutionTargetStatusLabel status="ready" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
