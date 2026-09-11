import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BrandProvider } from '../providers/brand'

import { AppMobileMasthead } from './AppMobileMasthead'
import type { DockState } from './useDockState'

const mockOnMobileToggle = vi.fn()
const mockUseDockState = vi.fn<() => DockState>()

vi.mock('./useDockState', () => ({
  useDockState: (): DockState => mockUseDockState(),
}))

describe('AppMobileMasthead', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseDockState.mockReturnValue({
      isDockExpanded: false,
      isDockTextExpanded: false,
      isMobile: true,
      dockedToggleRef: { current: null },
      mobileToggleRef: { current: null },
      onToggleDock: vi.fn(),
      onMobileToggle: mockOnMobileToggle,
      isDockExpandableExpanded: false,
      onNavToggle: vi.fn(),
      onNavSelect: vi.fn(),
    })
  })

  it('renders the hamburger toggle button', () => {
    render(
      <BrandProvider>
        <AppMobileMasthead />
      </BrandProvider>
    )
    expect(screen.getByRole('button', { name: 'Global navigation' })).toBeInTheDocument()
  })

  it('renders the home logo link', () => {
    render(
      <BrandProvider>
        <AppMobileMasthead />
      </BrandProvider>
    )
    const logoLink = screen.getByRole('link', { name: 'Home' })
    expect(logoLink).toBeInTheDocument()
    expect(logoLink).toHaveAttribute('href', '/')
  })

  it('renders the brand logo', () => {
    render(
      <BrandProvider>
        <AppMobileMasthead />
      </BrandProvider>
    )
    expect(screen.getByRole('img', { name: 'Syntara' })).toBeInTheDocument()
  })

  it('calls onMobileToggle when hamburger is clicked', async () => {
    const user = userEvent.setup()
    render(
      <BrandProvider>
        <AppMobileMasthead />
      </BrandProvider>
    )

    await user.click(screen.getByRole('button', { name: 'Global navigation' }))
    expect(mockOnMobileToggle).toHaveBeenCalledOnce()
  })

  it('renders correctly when dock is expanded', () => {
    mockUseDockState.mockReturnValue({
      isDockExpanded: true,
      isDockTextExpanded: false,
      isMobile: true,
      dockedToggleRef: { current: null },
      mobileToggleRef: { current: null },
      onToggleDock: vi.fn(),
      onMobileToggle: mockOnMobileToggle,
      isDockExpandableExpanded: false,
      onNavToggle: vi.fn(),
      onNavSelect: vi.fn(),
    })
    render(
      <BrandProvider>
        <AppMobileMasthead />
      </BrandProvider>
    )
    const toggle = screen.getByRole('button', { name: 'Global navigation' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })
})
