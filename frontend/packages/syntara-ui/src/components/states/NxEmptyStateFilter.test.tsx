import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { NxEmptyStateFilter } from './NxEmptyStateFilter'

describe('NxEmptyStateFilter', () => {
  it('has no accessibility violations with default props', async () => {
    const { container } = render(<NxEmptyStateFilter />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with action button', async () => {
    const { container } = render(<NxEmptyStateFilter clearAllFilters={vi.fn()} />)

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders with default title and description', () => {
    render(<NxEmptyStateFilter />)

    expect(screen.getByText('No results found')).toBeInTheDocument()
    expect(
      screen.getByText('No results match the filter criteria. Try changing your filter settings.')
    ).toBeInTheDocument()
  })

  it('renders with custom title', () => {
    render(<NxEmptyStateFilter title="Custom Title" />)

    expect(screen.getByText('Custom Title')).toBeInTheDocument()
  })

  it('renders with custom description', () => {
    render(<NxEmptyStateFilter description="Custom description text" />)

    expect(screen.getByText('Custom description text')).toBeInTheDocument()
  })

  it('shows clear filters button when clearAllFilters is provided', () => {
    const clearAllFilters = vi.fn()
    render(<NxEmptyStateFilter clearAllFilters={clearAllFilters} />)

    expect(screen.getByRole('button', { name: 'Clear all filters' })).toBeInTheDocument()
  })

  it('does not show clear filters button when clearAllFilters is not provided', () => {
    render(<NxEmptyStateFilter />)

    expect(screen.queryByRole('button', { name: 'Clear all filters' })).not.toBeInTheDocument()
  })

  it('calls clearAllFilters when button is clicked', async () => {
    const user = userEvent.setup()
    const clearAllFilters = vi.fn()
    render(<NxEmptyStateFilter clearAllFilters={clearAllFilters} />)

    await user.click(screen.getByRole('button', { name: 'Clear all filters' }))
    expect(clearAllFilters).toHaveBeenCalledTimes(1)
  })

  it('renders with custom button text', () => {
    const clearAllFilters = vi.fn()
    render(<NxEmptyStateFilter clearAllFilters={clearAllFilters} buttonText="Reset Filters" />)

    expect(screen.getByRole('button', { name: 'Reset Filters' })).toBeInTheDocument()
  })

  it('renders with custom image', () => {
    render(<NxEmptyStateFilter imageSrc="/test-image.png" imageAlt="Test alt text" />)

    const image = screen.getByRole('img', { name: 'Test alt text' })
    expect(image).toBeInTheDocument()
    expect(image).toHaveAttribute('src', '/test-image.png')
  })

  it('uses default alt text for image when not provided', () => {
    render(<NxEmptyStateFilter imageSrc="/test-image.png" />)

    const image = screen.getByRole('img', { name: 'No results' })
    expect(image).toBeInTheDocument()
  })

  it('renders all custom props together', () => {
    const clearAllFilters = vi.fn()
    render(
      <NxEmptyStateFilter
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
