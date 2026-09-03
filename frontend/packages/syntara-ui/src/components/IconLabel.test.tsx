import { RhUiCheckCircleIcon } from '@patternfly/react-icons'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { IconLabel } from './IconLabel'

describe('IconLabel', () => {
  it('renders children text', () => {
    render(<IconLabel>Edit workflow</IconLabel>)

    expect(screen.getByText('Edit workflow')).toBeInTheDocument()
  })

  it('renders with icon', () => {
    render(<IconLabel icon={<RhUiCheckCircleIcon data-testid="test-icon" />}>Success</IconLabel>)

    expect(screen.getByTestId('test-icon')).toBeInTheDocument()
    expect(screen.getByText('Success')).toBeInTheDocument()
  })

  it('renders without icon when not provided', () => {
    render(<IconLabel>Text only</IconLabel>)

    expect(screen.getByText('Text only')).toBeInTheDocument()
  })

  it('applies custom color style', () => {
    render(<IconLabel color="red">Colored text</IconLabel>)

    const flexContainer = screen.getByTestId('icon-label')
    expect(flexContainer).toHaveStyle({ color: 'red' })
  })

  it('does not apply color style when not provided', () => {
    render(<IconLabel>No color</IconLabel>)

    const flexContainer = screen.getByTestId('icon-label')
    expect(flexContainer).not.toHaveAttribute('style')
  })

  it('renders with icon and custom color', () => {
    render(
      <IconLabel icon={<RhUiCheckCircleIcon data-testid="icon" />} color="green">
        Success message
      </IconLabel>
    )

    expect(screen.getByTestId('icon')).toBeInTheDocument()
    expect(screen.getByText('Success message')).toBeInTheDocument()

    const flexContainer = screen.getByTestId('icon-label')
    expect(flexContainer).toHaveStyle({ color: 'green' })
  })

  it('renders complex children', () => {
    render(
      <IconLabel>
        <span data-testid="child-span">Complex</span> content
      </IconLabel>
    )

    expect(screen.getByTestId('child-span')).toBeInTheDocument()
    expect(screen.getByText('Complex')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<IconLabel icon={<RhUiCheckCircleIcon aria-hidden />}>Edit workflow</IconLabel>)
    expect(await axe(container)).toHaveNoViolations()
  })
})
