import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import { EXECUTION_PLANE_ENABLED_TOOLTIP, ExecutionPlaneEnabledState } from './ExecutionPlaneEnabledState'

describe('ExecutionPlaneEnabledState', () => {
  it('renders a static Enabled label when enabled', () => {
    render(<ExecutionPlaneEnabledState enabled />)

    expect(screen.getByText('Enabled')).toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })

  it('renders a static Disabled label when disabled', () => {
    render(<ExecutionPlaneEnabledState enabled={false} />)

    expect(screen.getByText('Disabled')).toBeInTheDocument()
    expect(screen.queryByText('Enabled')).not.toBeInTheDocument()
  })

  it('shows the execution-plane tooltip on hover', async () => {
    const user = userEvent.setup()
    render(<ExecutionPlaneEnabledState enabled />)

    await user.hover(screen.getByText('Enabled'))

    expect(await screen.findByText(EXECUTION_PLANE_ENABLED_TOOLTIP)).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExecutionPlaneEnabledState enabled />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
