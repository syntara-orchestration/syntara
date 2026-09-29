import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SynSelectFieldToggle } from './synSelectFieldToggle'

describe('SynSelectFieldToggle', () => {
  it('renders the display label', () => {
    render(
      <SynSelectFieldToggle
        toggleRef={null}
        displayLabel="Project One"
        isOpen={false}
        onToggle={vi.fn()}
        onBlur={vi.fn()}
        hasError={false}
      />
    )

    expect(screen.getByRole('button', { name: 'Project One' })).toBeInTheDocument()
  })

  it('marks the toggle as disabled when isDisabled is true', () => {
    render(
      <SynSelectFieldToggle
        toggleRef={null}
        displayLabel="Project One"
        isOpen={false}
        onToggle={vi.fn()}
        onBlur={vi.fn()}
        hasError={false}
        isDisabled
      />
    )

    expect(screen.getByRole('button', { name: 'Project One' })).toBeDisabled()
  })

  it('uses danger status when hasError is true', () => {
    render(
      <SynSelectFieldToggle
        toggleRef={null}
        displayLabel="Project One"
        isOpen={false}
        onToggle={vi.fn()}
        onBlur={vi.fn()}
        hasError
      />
    )

    expect(screen.getByRole('button', { name: 'Project One' })).toHaveClass('pf-m-danger')
  })

  it('calls onToggle when clicked', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(
      <SynSelectFieldToggle
        toggleRef={null}
        displayLabel="Project One"
        isOpen={false}
        onToggle={onToggle}
        onBlur={vi.fn()}
        hasError={false}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Project One' }))

    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})
