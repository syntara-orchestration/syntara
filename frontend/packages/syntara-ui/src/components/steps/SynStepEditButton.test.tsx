import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynStepEditButton } from './SynStepEditButton'

describe('SynStepEditButton', () => {
  it('calls onClick and stops click propagation', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    const onPanelClick = vi.fn()

    render(
      <div onClick={onPanelClick} onKeyDown={() => undefined} role="presentation">
        <SynStepEditButton stepTitle="Deploy" onClick={onEdit} />
      </div>
    )

    await user.click(screen.getByRole('button', { name: 'Edit Deploy' }))
    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(onPanelClick).not.toHaveBeenCalled()
  })

  it('merges optional className onto the button', () => {
    render(<SynStepEditButton stepTitle="Deploy" onClick={vi.fn()} className="custom-edit" />)

    expect(screen.getByRole('button', { name: 'Edit Deploy' })).toHaveClass('custom-edit')
  })

  it('has no axe violations', async () => {
    const { container } = render(<SynStepEditButton stepTitle="Deploy" onClick={vi.fn()} />)

    expect(await axe(container)).toHaveNoViolations()
  })
})
