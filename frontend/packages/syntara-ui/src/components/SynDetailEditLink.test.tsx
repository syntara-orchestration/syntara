import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { SynDetailEditLink } from './SynDetailEditLink'

describe('SynDetailEditLink', () => {
  it('renders as an anchor with href and primary button styling', () => {
    render(<SynDetailEditLink to="/items/1/edit">Edit item</SynDetailEditLink>)
    const link = screen.getByRole('link', { name: 'Edit item' })
    expect(link).toHaveAttribute('href', '/items/1/edit')
    expect(link).toHaveClass('pf-v6-c-button', 'pf-m-primary')
  })

  it('sets aria-disabled when isAriaDisabled is true', () => {
    render(
      <SynDetailEditLink to="/items/1/edit" isAriaDisabled>
        Edit item
      </SynDetailEditLink>
    )
    expect(screen.getByRole('link', { name: 'Edit item' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynDetailEditLink to="/items/1/edit">Edit item</SynDetailEditLink>)
    expect(await axe(container)).toHaveNoViolations()
  })
})
