import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { AppBreadcrumbItem } from '../../app/breadcrumbs/appBreadcrumbItem'

import { SynPageBreadcrumbsCollapsedMiddle } from './SynPageBreadcrumbsCollapsedMiddle'

const MIDDLE_ITEMS: readonly AppBreadcrumbItem[] = [
  { label: 'Mid A', href: '/a' },
  { label: 'Mid B', href: '/b' },
]

describe('SynPageBreadcrumbsCollapsedMiddle', () => {
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

  it('renders a toggle button with the item count', () => {
    render(<SynPageBreadcrumbsCollapsedMiddle middleItems={MIDDLE_ITEMS} />)
    expect(screen.getByRole('button', { name: 'Earlier pages, 2 levels' })).toBeInTheDocument()
  })

  it('opens the dropdown on toggle click and shows menu items', async () => {
    const user = userEvent.setup()
    render(<SynPageBreadcrumbsCollapsedMiddle middleItems={MIDDLE_ITEMS} />)

    await user.click(screen.getByRole('button', { name: 'Earlier pages, 2 levels' }))

    expect(screen.getByRole('menuitem', { name: 'Mid A' })).toHaveAttribute('href', '/a')
    expect(screen.getByRole('menuitem', { name: 'Mid B' })).toHaveAttribute('href', '/b')
  })

  it('uses client-side navigation on regular menu item click', async () => {
    const user = userEvent.setup()
    render(<SynPageBreadcrumbsCollapsedMiddle middleItems={MIDDLE_ITEMS} />)

    await user.click(screen.getByRole('button', { name: 'Earlier pages, 2 levels' }))

    let defaultPrevented: boolean | undefined
    document.addEventListener(
      'click',
      (e) => {
        defaultPrevented = e.defaultPrevented
      },
      { once: true }
    )

    await user.click(screen.getByRole('menuitem', { name: 'Mid A' }))

    expect(defaultPrevented).toBe(true)
  })

  it('allows modifier-key clicks to use default browser behavior', async () => {
    const user = userEvent.setup()
    render(<SynPageBreadcrumbsCollapsedMiddle middleItems={MIDDLE_ITEMS} />)

    await user.click(screen.getByRole('button', { name: 'Earlier pages, 2 levels' }))

    let defaultPrevented: boolean | undefined
    document.addEventListener(
      'click',
      (e) => {
        defaultPrevented = e.defaultPrevented
      },
      { once: true }
    )

    await user.keyboard('{Meta>}')
    await user.click(screen.getByRole('menuitem', { name: 'Mid A' }))
    await user.keyboard('{/Meta}')

    expect(defaultPrevented).toBe(false)
  })

  it('closes the dropdown after clicking a menu item', async () => {
    const user = userEvent.setup()
    render(<SynPageBreadcrumbsCollapsedMiddle middleItems={MIDDLE_ITEMS} />)

    const toggle = screen.getByRole('button', { name: 'Earlier pages, 2 levels' })
    await user.click(toggle)
    await user.click(screen.getByRole('menuitem', { name: 'Mid A' }))

    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders items without href as non-link menu entries', async () => {
    const user = userEvent.setup()
    const items: readonly AppBreadcrumbItem[] = [{ label: 'No link' }, { label: 'Has link', href: '/link' }]
    render(<SynPageBreadcrumbsCollapsedMiddle middleItems={items} />)

    await user.click(screen.getByRole('button', { name: 'Earlier pages, 2 levels' }))

    const noLinkItem = screen.getByRole('menuitem', { name: 'No link' })
    expect(noLinkItem).not.toHaveAttribute('href')
  })

  it('has no accessibility violations when the dropdown is open', async () => {
    const { Breadcrumb } = await import('@patternfly/react-core')
    const user = userEvent.setup()
    const { container } = render(
      <Breadcrumb>
        <SynPageBreadcrumbsCollapsedMiddle middleItems={MIDDLE_ITEMS} />
      </Breadcrumb>
    )

    await user.click(screen.getByRole('button', { name: 'Earlier pages, 2 levels' }))

    expect(await axe(container)).toHaveNoViolations()
  })
})
