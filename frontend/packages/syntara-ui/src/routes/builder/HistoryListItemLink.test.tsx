import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'

import * as routeRefs from '../../app/routes/routeReferences'

import { HistoryListItemLink } from './HistoryListItemLink'

const executionDestination = { to: routeRefs.executionDetailRoute.fullPath, params: { executionId: 'execution-1' } }

describe('HistoryListItemLink', () => {
  const onSelect = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders an anchor with the correct href', () => {
    render(<HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="test link" />)

    const link = screen.getByRole('link', { name: 'test link' })
    expect(link).toHaveAttribute('href', '/executions/execution-1')
  })

  it('applies the PF simple-list item-link class', () => {
    render(<HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="link" />)

    expect(screen.getByRole('link')).toHaveClass('pf-v6-c-simple-list__item-link')
  })

  it('applies the PF simple-list item-link class with a row overlay className', () => {
    render(
      <HistoryListItemLink
        options={executionDestination}
        onSelect={onSelect}
        className="row-overlay"
        aria-label="link"
      />
    )

    const link = screen.getByRole('link')
    expect(link).toHaveClass('pf-v6-c-simple-list__item-link')
    expect(link).toHaveClass('row-overlay')
  })

  it('appends custom className', () => {
    render(
      <HistoryListItemLink options={executionDestination} onSelect={onSelect} className="my-extra" aria-label="link" />
    )

    const link = screen.getByRole('link')
    expect(link).toHaveClass('pf-v6-c-simple-list__item-link')
    expect(link).toHaveClass('my-extra')
  })

  it('sets aria-current and pf-m-current when selected', () => {
    render(<HistoryListItemLink options={executionDestination} onSelect={onSelect} isSelected aria-label="link" />)

    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('aria-current', 'page')
    expect(link).toHaveClass('pf-m-current')
  })

  it('omits aria-current and pf-m-current when not selected', () => {
    render(<HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="link" />)

    const link = screen.getByRole('link')
    expect(link).not.toHaveAttribute('aria-current')
    expect(link).not.toHaveClass('pf-m-current')
  })

  it('sets data-item-id', () => {
    render(
      <HistoryListItemLink options={executionDestination} onSelect={onSelect} data-item-id="abc" aria-label="link" />
    )

    expect(screen.getByRole('link')).toHaveAttribute('data-item-id', 'abc')
  })

  it('calls onSelect on unmodified click', async () => {
    const user = userEvent.setup()
    render(<HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="link" />)

    await user.click(screen.getByRole('link'))

    expect(onSelect).toHaveBeenCalledTimes(1)
  })

  it('does not call onSelect on Ctrl+click', async () => {
    const user = userEvent.setup()
    render(<HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="link" />)

    await user.keyboard('{Control>}')
    await user.click(screen.getByRole('link'))
    await user.keyboard('{/Control}')

    expect(onSelect).not.toHaveBeenCalled()
  })

  it('does not call onSelect on Meta+click', async () => {
    const user = userEvent.setup()
    render(<HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="link" />)

    await user.keyboard('{Meta>}')
    await user.click(screen.getByRole('link'))
    await user.keyboard('{/Meta}')

    expect(onSelect).not.toHaveBeenCalled()
  })

  it('renders children', () => {
    render(
      <HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="link">
        <span>Row content</span>
      </HistoryListItemLink>
    )

    expect(screen.getByText('Row content')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <nav>
        <HistoryListItemLink options={executionDestination} onSelect={onSelect} aria-label="Test link" />
      </nav>
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when selected', async () => {
    const { container } = render(
      <nav>
        <HistoryListItemLink options={executionDestination} onSelect={onSelect} isSelected aria-label="Selected link" />
      </nav>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
