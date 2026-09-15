import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { useCanI } from '../hooks/useCanI'

import { ProtectedRoute } from './ProtectedRoute'

vi.mock('../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

describe('ProtectedRoute', () => {
  it('renders children when permission is granted', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })

    render(
      <ProtectedRoute action="create" resourceType="user">
        <div>Protected content</div>
      </ProtectedRoute>
    )

    expect(screen.getByText('Protected content')).toBeInTheDocument()
  })

  it('shows loading spinner while permission is checking', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: true, isError: false })

    render(
      <ProtectedRoute action="create" resourceType="user">
        <div>Protected content</div>
      </ProtectedRoute>
    )

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
    expect(screen.queryByText('Access denied')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('shows access denied when permission is denied', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    render(
      <ProtectedRoute action="create" resourceType="user">
        <div>Protected content</div>
      </ProtectedRoute>
    )

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Access denied', level: 2 })).toBeInTheDocument()
    expect(screen.getByText(/requires user:create/)).toBeInTheDocument()
  })

  it('shows error state when permission check fails', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: true })

    render(
      <ProtectedRoute action="create" resourceType="user">
        <div>Protected content</div>
      </ProtectedRoute>
    )

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
    expect(screen.queryByText('Access denied')).not.toBeInTheDocument()
    expect(screen.getByText('Unable to verify permissions')).toBeInTheDocument()
  })

  it('passes correct action and resourceType to useCanI', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })

    render(
      <ProtectedRoute action="update" resourceType="workflow">
        <div>Editor</div>
      </ProtectedRoute>
    )

    expect(useCanI).toHaveBeenCalledWith('update', 'workflow')
  })

  it('has no accessibility violations when access is denied', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    const { container } = render(
      <ProtectedRoute action="create" resourceType="user">
        <div>Protected content</div>
      </ProtectedRoute>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when access is granted', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })

    const { container } = render(
      <ProtectedRoute action="create" resourceType="user">
        <div>Protected content</div>
      </ProtectedRoute>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
