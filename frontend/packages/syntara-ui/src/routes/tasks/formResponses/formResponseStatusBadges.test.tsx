import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FormResponseStatusBadges } from './formResponseStatusBadges'

describe('FormResponseStatusBadges', () => {
  it('renders pending status', () => {
    render(<FormResponseStatusBadges status="pending" />)
    expect(screen.getByText('Pending')).toBeInTheDocument()
  })

  it('renders expired status as Timed out', () => {
    render(<FormResponseStatusBadges status="expired" />)
    expect(screen.getByText('Timed out')).toBeInTheDocument()
  })

  it('renders nothing when status is missing', () => {
    const { container } = render(<FormResponseStatusBadges status={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
