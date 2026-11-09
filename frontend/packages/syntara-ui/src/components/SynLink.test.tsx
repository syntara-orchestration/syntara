import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import '../app/tanstackRouter'
import * as routeRefs from '../app/routes/routeReferences'

import { SynLink } from './SynLink'

const workflowsDestination = { to: routeRefs.workflowsRoute.fullPath }

describe('SynLink', () => {
  it('renders as an anchor tag with the correct href', () => {
    render(<SynLink options={workflowsDestination}>Go somewhere</SynLink>)
    expect(screen.getByRole('link', { name: 'Go somewhere' })).toHaveAttribute('href', '/workflows')
  })

  it('applies PatternFly link button classes', () => {
    render(<SynLink options={workflowsDestination}>Link</SynLink>)
    const link = screen.getByRole('link', { name: 'Link' })
    expect(link).toHaveClass('pf-v6-c-button', 'pf-m-link', 'pf-m-inline')
  })

  it('merges custom className with PatternFly classes', () => {
    render(
      <SynLink options={workflowsDestination} className="my-class">
        Link
      </SynLink>
    )
    const link = screen.getByRole('link', { name: 'Link' })
    expect(link).toHaveClass('pf-v6-c-button', 'pf-m-link', 'pf-m-inline', 'my-class')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynLink options={workflowsDestination}>Accessible link</SynLink>)
    expect(await axe(container)).toHaveNoViolations()
  })
})
