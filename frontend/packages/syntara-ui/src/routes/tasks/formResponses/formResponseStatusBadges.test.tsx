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

  it('renders submitted status', () => {
    render(<FormResponseStatusBadges status="submitted" />)
    expect(screen.getByText('Submitted')).toBeInTheDocument()
  })

  it('renders cancelled status', () => {
    render(<FormResponseStatusBadges status="cancelled" />)
    expect(screen.getByText('Cancelled')).toBeInTheDocument()
  })

  it('renders nothing when status is missing', () => {
    const { container } = render(<FormResponseStatusBadges status={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
