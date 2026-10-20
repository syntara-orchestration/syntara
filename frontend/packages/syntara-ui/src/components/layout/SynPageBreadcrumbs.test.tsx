import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynPageBreadcrumbs } from './SynPageBreadcrumbs'

function stubNarrowViewport() {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: query === '(max-width: 768px)',
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  )
}

describe('SynPageBreadcrumbs', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }))
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns null when fewer than two items', () => {
    render(<SynPageBreadcrumbs items={[{ label: 'Only' }]} />)
    expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).not.toBeInTheDocument()
  })

  it('renders links and current page', () => {
    render(<SynPageBreadcrumbs items={[{ label: 'Parent', href: '/parent' }, { label: 'Current' }]} />)

    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument()
    const parentLink = screen.getByRole('link', { name: 'Parent' })
    expect(parentLink).toHaveAttribute('href', '/parent')
    expect(screen.getByText('Current')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SynPageBreadcrumbs
        items={[{ label: 'One', href: '/one' }, { label: 'Two', href: '/two' }, { label: 'Three' }]}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('uses a dropdown toggle on narrow viewports when the trail has many segments', () => {
    stubNarrowViewport()

    render(
      <SynPageBreadcrumbs
        items={[
          { label: 'First', href: '/first' },
          { label: 'Mid A', href: '/a' },
          { label: 'Mid B', href: '/b' },
          { label: 'Last' },
        ]}
      />
    )

    expect(screen.getByRole('link', { name: 'First' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Mid A' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Earlier pages, 2 levels' })).toBeInTheDocument()
    expect(screen.getByText('Last')).toBeInTheDocument()
  })

  it('on narrow viewport, toggling the badge opens the menu with navigable middle segments', async () => {
    const user = userEvent.setup()
    stubNarrowViewport()

    render(
      <SynPageBreadcrumbs
        items={[
          { label: 'First', href: '/first' },
          { label: 'Mid A', href: '/a' },
          { label: 'Mid B', href: '/b' },
          { label: 'Last' },
        ]}
      />
    )

    const toggle = screen.getByRole('button', { name: 'Earlier pages, 2 levels' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    const itemA = screen.getByRole('menuitem', { name: 'Mid A' })
    expect(itemA).toHaveAttribute('href', '/a')
    const itemB = screen.getByRole('menuitem', { name: 'Mid B' })
    expect(itemB).toHaveAttribute('href', '/b')

    await user.click(toggle)

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('truncates the current-page label and shows the full name in a tooltip on hover and keyboard focus', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn()
        disconnect = vi.fn()
        unobserve = vi.fn()
      }
    )

    const longLabel = `Project ${'x'.repeat(200)}`

    render(
      <div style={{ width: 160 }}>
        <SynPageBreadcrumbs
          items={[{ label: 'Access management', href: '/access-management' }, { label: longLabel }]}
        />
      </div>
    )

    const currentSegment = screen.getByTestId('breadcrumb-current-segment')
    expect(currentSegment).toHaveTextContent(longLabel)

    expect(currentSegment).toHaveClass('pf-v6-c-truncate')

    await user.hover(currentSegment)

    await waitFor(() => {
      expect(screen.getByRole('tooltip')).toHaveTextContent(longLabel)
    })

    const parentCrumb = screen.getByRole('link', { name: 'Access management' })
    await user.tab()
    expect(parentCrumb).toHaveFocus()

    await user.tab()
    await user.tab()
    expect(currentSegment).toHaveFocus()

    await waitFor(() => {
      expect(screen.getByRole('tooltip')).toHaveTextContent(longLabel)
    })
  })

  it('truncates a long linked middle segment on a wide viewport with four crumbs', () => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn()
        disconnect = vi.fn()
        unobserve = vi.fn()
      }
    )

    const longProject = `alice-sandbox-${'x'.repeat(80)}`

    render(
      <div style={{ width: 480 }}>
        <SynPageBreadcrumbs
          items={[
            { label: 'Access management', href: '/access-management' },
            { label: 'Projects', href: '/access-management/projects' },
            { label: longProject, href: '/access-management/projects/1' },
            { label: 'Workflows' },
          ]}
        />
      </div>
    )

    expect(screen.getByRole('link', { name: longProject })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Projects' })).toBeInTheDocument()
    expect(
      screen.getAllByTestId('breadcrumb-truncated-label').some((node) => node.textContent?.includes(longProject))
    ).toBe(true)
    expect(screen.getByTestId('breadcrumb-current-segment')).toHaveTextContent('Workflows')
  })

  it('renders a non-link middle segment in the full trail (wide viewport)', () => {
    render(
      <SynPageBreadcrumbs items={[{ label: 'Home', href: '/home' }, { label: 'Unlinked step' }, { label: 'Done' }]} />
    )

    expect(screen.getByText('Unlinked step')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Unlinked step' })).not.toBeInTheDocument()
  })

  it('on narrow viewport, supports a first crumb without href when collapsing middle segments', () => {
    stubNarrowViewport()

    render(
      <SynPageBreadcrumbs
        items={[
          { label: 'Section' },
          { label: 'Mid A', href: '/a' },
          { label: 'Mid B', href: '/b' },
          { label: 'Last' },
        ]}
      />
    )

    expect(screen.queryByRole('link', { name: 'Section' })).not.toBeInTheDocument()
    expect(screen.getByText('Section')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Earlier pages, 2 levels' })).toBeInTheDocument()
  })

  it('renders middle items without href as non-link entries in the collapsed dropdown', async () => {
    const user = userEvent.setup()
    stubNarrowViewport()

    render(
      <SynPageBreadcrumbs
        items={[
          { label: 'First', href: '/first' },
          { label: 'Mid no href' },
          { label: 'Mid B', href: '/b' },
          { label: 'Last' },
        ]}
      />
    )

    const toggle = screen.getByRole('button', { name: 'Earlier pages, 2 levels' })
    await user.click(toggle)

    const midItem = screen.getByRole('menuitem', { name: 'Mid no href' })
    expect(midItem).toBeInTheDocument()
    expect(midItem).not.toHaveAttribute('href')
  })

  it('closes dropdown after selecting a middle segment link', async () => {
    const user = userEvent.setup()
    stubNarrowViewport()

    render(
      <SynPageBreadcrumbs
        items={[
          { label: 'First', href: '/first' },
          { label: 'Mid A', href: '/a' },
          { label: 'Mid B', href: '/b' },
          { label: 'Last' },
        ]}
      />
    )

    const toggle = screen.getByRole('button', { name: 'Earlier pages, 2 levels' })
    await user.click(toggle)
    await user.click(screen.getByRole('menuitem', { name: 'Mid A' }))
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })
})
