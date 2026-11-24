import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RunDetailsPanelExpandButton } from './RunDetailsPanelExpandButton'

describe('RunDetailsPanelExpandButton', () => {
  it('shows expand tooltip and toggles when collapsed', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()

    render(<RunDetailsPanelExpandButton isExpanded={false} onToggle={onToggle} />)

    const button = screen.getByRole('button', { name: 'Expand panel' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    await user.hover(button)
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Expand panel')

    await user.click(button)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('shows collapse state when expanded', () => {
    render(<RunDetailsPanelExpandButton isExpanded onToggle={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Collapse panel' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('has no axe violations', async () => {
    const { container } = render(<RunDetailsPanelExpandButton isExpanded={false} onToggle={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
