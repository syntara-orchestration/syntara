import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { axe } from 'vitest-axe'

import { SynPageHeader } from './SynPageHeader'

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

describe('SynPageHeader', () => {
  it('renders string title as heading', () => {
    render(<SynPageHeader title="Test Title" />)

    expect(screen.getByRole('heading', { name: 'Test Title' })).toBeInTheDocument()
  })

  it('renders without toolbar when toolbar is omitted', () => {
    render(<SynPageHeader title="No Toolbar" />)

    expect(screen.queryByRole('toolbar')).not.toBeInTheDocument()
  })

  it('renders toolbar actions', () => {
    render(
      <SynPageHeader
        title="With Actions"
        toolbar={
          <>
            <button type="button">Action 1</button>
            <button type="button">Action 2</button>
          </>
        }
      />
    )

    expect(screen.getByRole('button', { name: 'Action 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Action 2' })).toBeInTheDocument()
  })

  it('renders heading at h1 level', () => {
    render(<SynPageHeader title="Main Heading" />)

    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('Main Heading')
  })

  it('does not render breadcrumbs when fewer than two items', () => {
    render(<SynPageHeader title="Page" breadcrumbs={[{ label: 'Only' }]} />)

    expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Page' })).toBeInTheDocument()
  })

  it('renders breadcrumbs above the title when two or more items', () => {
    render(
      <SynPageHeader
        title="Create user"
        breadcrumbs={[
          { label: 'Access management', href: '/system-administration/access-management' },
          { label: 'Users', href: '/system-administration/access-management/users' },
          { label: 'Create user' },
        ]}
      />
    )

    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Users' })).toHaveAttribute(
      'href',
      '/system-administration/access-management/users'
    )
    expect(screen.getByRole('heading', { name: 'Create user' })).toBeInTheDocument()
  })

  it('renders doc link button when docLink is provided', () => {
    render(<SynPageHeader title="Workflows" docLink="https://docs.ansible.com/workflows" />)

    const link = screen.getByRole('link', { name: /View documentation/i })
    expect(link).toHaveAttribute('href', 'https://docs.ansible.com/workflows')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('does not render doc link button when docLink is omitted', () => {
    render(<SynPageHeader title="Workflows" />)

    expect(screen.queryByRole('link', { name: /View documentation/i })).not.toBeInTheDocument()
  })

  it('has no accessibility violations with breadcrumbs', async () => {
    const { container } = render(
      <SynPageHeader
        title="Settings"
        breadcrumbs={[
          { label: 'Configuration', href: '/configuration/integrations' },
          { label: 'Settings', href: '/system-administration/settings' },
          { label: 'System' },
        ]}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
