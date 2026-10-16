import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FormPromptActionButtons } from './FormPromptActionButtons'

describe('FormPromptActionButtons', () => {
  it('calls onRespondClick when enabled', async () => {
    const user = userEvent.setup()
    const onRespondClick = vi.fn()

    render(<FormPromptActionButtons onRespondClick={onRespondClick} />)

    await user.click(screen.getByRole('button', { name: 'Respond to prompt' }))
    expect(onRespondClick).toHaveBeenCalledOnce()
  })

  it('does not call onRespondClick when disabled', async () => {
    const user = userEvent.setup()
    const onRespondClick = vi.fn()

    render(<FormPromptActionButtons isDisabled onRespondClick={onRespondClick} />)

    await user.click(screen.getByRole('button', { name: 'Respond to prompt' }))
    expect(onRespondClick).not.toHaveBeenCalled()
  })

  it('does not call onRespondClick when loading', async () => {
    const user = userEvent.setup()
    const onRespondClick = vi.fn()

    render(<FormPromptActionButtons isLoading onRespondClick={onRespondClick} />)

    const button = screen.queryByRole('button', { name: 'Respond to prompt' })
    if (button) {
      await user.click(button)
    }
    expect(onRespondClick).not.toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<FormPromptActionButtons onRespondClick={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
