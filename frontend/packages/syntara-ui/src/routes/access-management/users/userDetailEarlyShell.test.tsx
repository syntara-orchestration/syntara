import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynErrorState } from '../../../components/states/SynErrorState'

import { renderUserDetailEarlyShell } from './userDetailEarlyShell'

describe('renderUserDetailEarlyShell', () => {
  it('shows loading state for My Profile while /me query is pending', () => {
    render(
      renderUserDetailEarlyShell({
        isMyProfile: true,
        isMeQueryPending: true,
        hasUserQueryError: false,
        queryState: null,
        navigateBack: vi.fn(),
        refetchUser: vi.fn(),
      })
    )

    expect(screen.getByRole('heading', { name: 'My Profile' })).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Loading' })).toBeInTheDocument()
  })

  it('has no accessibility violations on My Profile loading state', async () => {
    const { container } = render(
      renderUserDetailEarlyShell({
        isMyProfile: true,
        isMeQueryPending: true,
        hasUserQueryError: false,
        queryState: null,
        navigateBack: vi.fn(),
        refetchUser: vi.fn(),
      })
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows not-found state with workflows back label for My Profile errors', async () => {
    const user = userEvent.setup()
    const navigateBack = vi.fn()
    const refetchUser = vi.fn().mockResolvedValue(undefined)

    render(
      renderUserDetailEarlyShell({
        isMyProfile: true,
        isMeQueryPending: false,
        hasUserQueryError: true,
        queryState: null,
        navigateBack,
        refetchUser,
      })
    )

    expect(screen.getByRole('button', { name: 'Back to workflows' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Back to workflows' }))
    expect(navigateBack).toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetchUser).toHaveBeenCalledOnce()
  })

  it('shows not-found state with default back label for admin user detail errors', async () => {
    const user = userEvent.setup()
    const navigateBack = vi.fn()
    const refetchUser = vi.fn().mockResolvedValue(undefined)

    render(
      renderUserDetailEarlyShell({
        isMyProfile: false,
        isMeQueryPending: false,
        hasUserQueryError: true,
        queryState: null,
        navigateBack,
        refetchUser,
      })
    )

    expect(screen.getByRole('button', { name: 'Back to users' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Back to users' }))
    expect(navigateBack).toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetchUser).toHaveBeenCalledOnce()
  })

  it('renders queryState for My Profile without breadcrumbs', () => {
    render(
      renderUserDetailEarlyShell({
        isMyProfile: true,
        isMeQueryPending: false,
        hasUserQueryError: false,
        queryState: <SynErrorState title="Error loading profile" message="Network error" onRetry={vi.fn()} />,
        navigateBack: vi.fn(),
        refetchUser: vi.fn(),
      })
    )

    expect(screen.getByRole('heading', { name: 'My Profile' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Error loading profile' })).toBeInTheDocument()
  })

  it('has no accessibility violations on admin user not-found state', async () => {
    const { container } = render(
      renderUserDetailEarlyShell({
        isMyProfile: false,
        isMeQueryPending: false,
        hasUserQueryError: true,
        queryState: null,
        navigateBack: vi.fn(),
        refetchUser: vi.fn(),
      })
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders queryState inside the early shell when provided', () => {
    render(
      renderUserDetailEarlyShell({
        isMyProfile: false,
        isMeQueryPending: false,
        hasUserQueryError: false,
        queryState: <SynErrorState title="Error loading user" message="Network error" onRetry={vi.fn()} />,
        navigateBack: vi.fn(),
        refetchUser: vi.fn(),
      })
    )

    expect(screen.getByRole('heading', { name: 'Error loading user' })).toBeInTheDocument()
  })

  it('returns null when no early-exit condition applies', () => {
    const { container } = render(
      renderUserDetailEarlyShell({
        isMyProfile: false,
        isMeQueryPending: false,
        hasUserQueryError: false,
        queryState: null,
        navigateBack: vi.fn(),
        refetchUser: vi.fn(),
      })
    )

    expect(container).toBeEmptyDOMElement()
  })
})
