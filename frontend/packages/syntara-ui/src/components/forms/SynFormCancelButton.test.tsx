import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynFormCancelButton } from './SynFormCancelButton'

vi.mock('../SynLink', () => ({
  SynLink: ({ to, children }: { to: string; children: ReactNode }) => (
    <a href={to} data-testid="syn-form-cancel-link">
      {children}
    </a>
  ),
}))

describe('SynFormCancelButton', () => {
  it('renders a link-styled button when only onClick is provided', () => {
    render(<SynFormCancelButton onClick={vi.fn()} />)

    const cancel = screen.getByRole('button', { name: 'Cancel' })
    expect(cancel).toHaveClass('pf-m-link')
  })

  it('calls onClick when the cancel button is clicked', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<SynFormCancelButton onClick={onClick} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('renders SynLink when to is provided', () => {
    render(<SynFormCancelButton to="/users" />)

    const link = screen.getByTestId('syn-form-cancel-link')
    expect(link).toHaveAttribute('href', '/users')
    expect(link).toHaveTextContent('Cancel')
  })

  it('renders a disabled link button when to is set and isDisabled is true', () => {
    render(<SynFormCancelButton to="/users" isDisabled />)

    const cancel = screen.getByRole('button', { name: 'Cancel' })
    expect(cancel).toHaveClass('pf-m-link')
    expect(cancel).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByTestId('syn-form-cancel-link')).not.toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynFormCancelButton onClick={vi.fn()} />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
