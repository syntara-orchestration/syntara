import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynStepEditButton } from './SynStepEditButton'

describe('SynStepEditButton', () => {
  it('has no axe violations', async () => {
    const { container } = render(<SynStepEditButton stepTitle="Deploy app" onClick={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('calls onClick with an accessible edit label', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()

    render(<SynStepEditButton stepTitle="Deploy app" onClick={onClick} />)

    const button = screen.getByRole('button', { name: 'Edit Deploy app' })
    expect(button).toHaveTextContent('Edit')
    await user.click(button)

    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
