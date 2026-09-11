import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SynDetail } from './SynDetail'

describe('Detail', () => {
  it('renders label and children', () => {
    render(<SynDetail label="Name">John Doe</SynDetail>)

    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('John Doe')).toBeInTheDocument()
  })

  it('returns null when children is undefined', () => {
    const { container } = render(<SynDetail label="Empty">{undefined}</SynDetail>)

    expect(container).toBeEmptyDOMElement()
  })

  it('returns null when children is null', () => {
    const { container } = render(<SynDetail label="Null">{null}</SynDetail>)

    expect(container).toBeEmptyDOMElement()
  })

  it('renders with string children', () => {
    render(<SynDetail label="Status">Active</SynDetail>)

    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('renders with number children', () => {
    render(<SynDetail label="Count">{42}</SynDetail>)

    expect(screen.getByText('Count')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders with JSX children', () => {
    render(
      <SynDetail label="Custom">
        <span data-testid="custom-child">Custom content</span>
      </SynDetail>
    )

    expect(screen.getByText('Custom')).toBeInTheDocument()
    expect(screen.getByTestId('custom-child')).toBeInTheDocument()
  })

  // Intentionally use getByText rather than data-testid: Detail is rendered multiple times
  // inside a single Details list, so hardcoded data-testid values would be non-unique.
  it('renders label in DescriptionListTerm', () => {
    render(<SynDetail label="Term Label">Value</SynDetail>)

    expect(screen.getByText('Term Label')).toBeInTheDocument()
  })

  it('renders children in DescriptionListDescription', () => {
    render(<SynDetail label="Label">Description Value</SynDetail>)

    expect(screen.getByText('Description Value')).toBeInTheDocument()
  })

  it('renders with empty string children (falsy but valid)', () => {
    const { container } = render(<SynDetail label="Empty String">{''}</SynDetail>)

    // Empty string is falsy, but it's a valid React child
    // The component checks !props.children which is true for empty string
    expect(container).toBeEmptyDOMElement()
  })

  it('returns null for zero value (falsy check)', () => {
    // The component uses !props.children which is true for 0
    // This is the actual behavior - zero is treated as falsy
    const { container } = render(<SynDetail label="Zero">{0}</SynDetail>)

    expect(container).toBeEmptyDOMElement()
  })
})
