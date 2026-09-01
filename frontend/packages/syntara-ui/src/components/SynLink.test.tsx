import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynLink } from './SynLink'

describe('SynLink', () => {
  it('renders as an anchor tag with the correct href', () => {
    render(<SynLink to="/some/path">Go somewhere</SynLink>)
    expect(screen.getByRole('link', { name: 'Go somewhere' })).toHaveAttribute('href', '/some/path')
  })

  it('applies PatternFly link button classes', () => {
    render(<SynLink to="/path">Link</SynLink>)
    const link = screen.getByRole('link', { name: 'Link' })
    expect(link).toHaveClass('pf-v6-c-button', 'pf-m-link', 'pf-m-inline')
  })

  it('merges custom className with PatternFly classes', () => {
    render(
      <SynLink to="/path" className="my-class">
        Link
      </SynLink>
    )
    const link = screen.getByRole('link', { name: 'Link' })
    expect(link).toHaveClass('pf-v6-c-button', 'pf-m-link', 'pf-m-inline', 'my-class')
  })

  it('invokes onClick when the link is activated', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(
      <SynLink to="/path" onClick={onClick}>
        Click me
      </SynLink>
    )

    await user.click(screen.getByRole('link', { name: 'Click me' }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynLink to="/path">Accessible link</SynLink>)
    expect(await axe(container)).toHaveNoViolations()
  })
})
