import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AppBreadcrumbItem } from '../../app/breadcrumbs/appBreadcrumbItem'

import { DetailPageShell } from './DetailPageShell'

vi.mock('../../components/layout/SynPageHeader', () => ({
  SynPageHeader: ({ title, breadcrumbs }: { title: React.ReactNode; breadcrumbs?: readonly AppBreadcrumbItem[] }) => (
    <div data-testid="syn-page-header">
      <h1>{title}</h1>
      {breadcrumbs && breadcrumbs.length >= 2 && (
        <nav aria-label="Breadcrumb">
          {breadcrumbs.map((b) =>
            b.href ? (
              <a key={b.label} href={b.href}>
                {b.label}
              </a>
            ) : (
              <span key={b.label}>{b.label}</span>
            )
          )}
        </nav>
      )}
    </div>
  ),
}))

const testBreadcrumbs: readonly AppBreadcrumbItem[] = [
  { label: 'Home', href: '/' },
  { label: 'Users', href: '/users' },
  { label: 'Details' },
]

describe('DetailPageShell', () => {
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

  it('has no accessibility violations', async () => {
    const { container } = render(
      <DetailPageShell title="Test Title">
        <p>Test content</p>
      </DetailPageShell>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with breadcrumbs', async () => {
    const { container } = render(
      <DetailPageShell title="Test Title" breadcrumbs={testBreadcrumbs}>
        <p>Test content</p>
      </DetailPageShell>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders the title and children', () => {
    render(
      <DetailPageShell title="Project Details">
        <p>Some content here</p>
      </DetailPageShell>
    )
    expect(screen.getByText('Project Details')).toBeInTheDocument()
    expect(screen.getByText('Some content here')).toBeInTheDocument()
  })

  it('renders breadcrumb navigation when two or more items are provided', () => {
    render(
      <DetailPageShell
        title="User Details"
        breadcrumbs={[
          { label: 'Access management', href: '/access-management' },
          { label: 'Users', href: '/access-management/users' },
          { label: 'User Details' },
        ]}
      >
        <p>Content</p>
      </DetailPageShell>
    )

    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument()
  })

  it('renders with a string title', () => {
    render(
      <DetailPageShell title="Custom Title" breadcrumbs={testBreadcrumbs}>
        <div>Child content</div>
      </DetailPageShell>
    )

    expect(screen.getByRole('heading', { name: 'Custom Title' })).toBeInTheDocument()
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('does not render breadcrumb navigation for fewer than two items', () => {
    render(
      <DetailPageShell title="Only Title" breadcrumbs={[{ label: 'Single item' }]}>
        <p>Content</p>
      </DetailPageShell>
    )

    // With only 1 breadcrumb item, SynPageHeader doesn't show breadcrumbs (requires ≥2)
    expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).not.toBeInTheDocument()
    expect(screen.getByText('Only Title')).toBeInTheDocument()
  })
})
