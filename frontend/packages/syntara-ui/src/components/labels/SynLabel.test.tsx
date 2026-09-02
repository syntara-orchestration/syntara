import { RhUiCheckCircleIcon } from '@patternfly/react-icons'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'

import { SynLabel } from './SynLabel'

describe('SynLabel', () => {
  it('renders children text', () => {
    render(<SynLabel>Completed</SynLabel>)

    expect(screen.getByText('Completed')).toBeInTheDocument()
  })

  it('renders icon when provided', () => {
    render(
      <SynLabel status="success" icon={<RhUiCheckCircleIcon data-testid="label-icon" />}>
        Success
      </SynLabel>
    )

    expect(screen.getByTestId('label-icon')).toBeInTheDocument()
  })

  it('defaults to compact size', () => {
    render(<SynLabel data-testid="label">Default</SynLabel>)

    expect(screen.getByTestId('label')).toHaveClass('pf-m-compact')
  })

  it('renders full-size when isCompact is false', () => {
    render(
      <SynLabel data-testid="label" isCompact={false}>
        Full Size
      </SynLabel>
    )

    expect(screen.getByTestId('label')).not.toHaveClass('pf-m-compact')
  })

  it('defaults to filled variant', () => {
    render(<SynLabel data-testid="label">Filled</SynLabel>)

    expect(screen.getByTestId('label')).not.toHaveClass('pf-m-outline')
  })

  it('renders outline variant when specified', () => {
    render(
      <SynLabel data-testid="label" variant="outline">
        Outline
      </SynLabel>
    )

    expect(screen.getByTestId('label')).toHaveClass('pf-m-outline')
  })

  it('forwards color prop', () => {
    render(<SynLabel color="blue">Blue</SynLabel>)

    expect(screen.getByText('Blue')).toBeInTheDocument()
  })

  it('re-renders correctly when props change', () => {
    const { rerender } = render(<SynLabel data-testid="label">First</SynLabel>)

    expect(screen.getByText('First')).toBeInTheDocument()
    expect(screen.getByTestId('label')).toHaveClass('pf-m-compact')

    rerender(
      <SynLabel data-testid="label" isCompact={false} variant="outline">
        Second
      </SynLabel>
    )

    expect(screen.getByText('Second')).toBeInTheDocument()
    expect(screen.getByTestId('label')).not.toHaveClass('pf-m-compact')
    expect(screen.getByTestId('label')).toHaveClass('pf-m-outline')
  })

  it('re-renders when only children change (same isCompact and variant)', () => {
    const { rerender } = render(<SynLabel>First content</SynLabel>)

    expect(screen.getByText('First content')).toBeInTheDocument()

    rerender(<SynLabel>Updated content</SynLabel>)

    expect(screen.getByText('Updated content')).toBeInTheDocument()
  })

  it('uses cached output when re-rendered with no prop changes', () => {
    function StableParent() {
      return <SynLabel data-testid="label">Cached</SynLabel>
    }

    const { rerender } = render(<StableParent />)

    rerender(<StableParent />)

    expect(screen.getByTestId('label')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SynLabel status="success" icon={<RhUiCheckCircleIcon />}>
        Completed
      </SynLabel>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
