import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { DescriptionExpandableContent } from './DescriptionExpandableContent'

describe('DescriptionExpandableContent', () => {
  it('renders the description under a Description term', () => {
    render(<DescriptionExpandableContent description="Token for GitHub API access" />)

    expect(screen.getByText('Description')).toBeInTheDocument()
    expect(screen.getByText('Token for GitHub API access')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<DescriptionExpandableContent description="Accessible description" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
