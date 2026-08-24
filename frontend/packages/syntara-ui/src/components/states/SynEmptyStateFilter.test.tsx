import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynEmptyStateFilter } from './SynEmptyStateFilter'

describe('SynEmptyStateFilter', () => {
  it('has no accessibility violations with default props', async () => {
    const { container } = render(<SynEmptyStateFilter />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with action button', async () => {
    const { container } = render(<SynEmptyStateFilter clearAllFilters={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders with default title and description', () => {
    render(<SynEmptyStateFilter />)

    expect(screen.getByText('No results found')).toBeInTheDocument()
    expect(
      screen.getByText('No results match the filter criteria. Try changing your filter settings.')
    ).toBeInTheDocument()
  })

  it('renders with custom title', () => {
    render(<SynEmptyStateFilter title="Custom Title" />)

    expect(screen.getByText('Custom Title')).toBeInTheDocument()
  })

  it('renders with custom description', () => {
    render(<SynEmptyStateFilter description="Custom description text" />)

    expect(screen.getByText('Custom description text')).toBeInTheDocument()
  })

  it('shows clear filters button when clearAllFilters is provided', () => {
    const clearAllFilters = vi.fn()
    render(<SynEmptyStateFilter clearAllFilters={clearAllFilters} />)

    expect(screen.getByRole('button', { name: 'Clear all filters' })).toBeInTheDocument()
  })

  it('does not show clear filters button when clearAllFilters is not provided', () => {
    render(<SynEmptyStateFilter />)

    expect(screen.queryByRole('button', { name: 'Clear all filters' })).not.toBeInTheDocument()
  })

  it('calls clearAllFilters when button is clicked', async () => {
    const user = userEvent.setup()
    const clearAllFilters = vi.fn()
    render(<SynEmptyStateFilter clearAllFilters={clearAllFilters} />)

    await user.click(screen.getByRole('button', { name: 'Clear all filters' }))
    expect(clearAllFilters).toHaveBeenCalledTimes(1)
  })

  it('renders with custom button text', () => {
    const clearAllFilters = vi.fn()
    render(<SynEmptyStateFilter clearAllFilters={clearAllFilters} buttonText="Reset Filters" />)

    expect(screen.getByRole('button', { name: 'Reset Filters' })).toBeInTheDocument()
  })

  it('renders with custom image', () => {
    render(<SynEmptyStateFilter imageSrc="/test-image.png" imageAlt="Test alt text" />)

    const image = screen.getByRole('img', { name: 'Test alt text' })
    expect(image).toBeInTheDocument()
    expect(image).toHaveAttribute('src', '/test-image.png')
  })

  it('uses default alt text for image when not provided', () => {
    render(<SynEmptyStateFilter imageSrc="/test-image.png" />)

    const image = screen.getByRole('img', { name: 'No results' })
    expect(image).toBeInTheDocument()
  })

  it('renders all custom props together', () => {
    const clearAllFilters = vi.fn()
    render(
      <SynEmptyStateFilter
        title="No Matches"
        description="Try different search terms"
        buttonText="Clear Search"
        imageSrc="/empty.png"
        imageAlt="Empty state"
        clearAllFilters={clearAllFilters}
      />
    )

    expect(screen.getByText('No Matches')).toBeInTheDocument()
    expect(screen.getByText('Try different search terms')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear Search' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Empty state' })).toBeInTheDocument()
  })
})
