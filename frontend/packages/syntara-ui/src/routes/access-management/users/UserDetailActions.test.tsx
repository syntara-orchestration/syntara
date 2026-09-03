import type { User } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { DialogState } from '../../../hooks/useDialogState'

import { UserDetailConfirmationDialogs, UserDetailToolbar } from './UserDetailActions'

const mockUser: User = {
  id: 'user-1',
  username: 'test-user',
  email: 'test@example.com',
  first_name: 'Test',
  last_name: 'User',
  is_enabled: true,
  is_builtin: false,
  auth_type: 'local',
  last_login: '2026-03-28T09:15:00Z',
  created_at: '2026-01-15T00:00:00Z',
  updated_at: '2026-02-10T00:00:00Z',
}

const fullPermissions = {
  canCreate: true,
  canUpdate: true,
  canDelete: true,
  canRevoke: true,
  isLoading: false,
  tooltips: {
    create: '',
    update: '',
    delete: '',
    revoke: '',
  },
}

function buildDialogState<T>(item: T | null, isOpen = true): DialogState<T> {
  return {
    isOpen,
    item,
    open: vi.fn(),
    close: vi.fn(),
  }
}

describe('UserDetailToolbar', () => {
  it('renders Edit user and kebab actions when the menu is shown', async () => {
    const user = userEvent.setup()

    render(
      <UserDetailToolbar
        permissions={fullPermissions}
        showKebabMenu
        onEdit={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    const editButton = screen.getByRole('button', { name: 'Edit user' })
    expect(editButton).toBeInTheDocument()
    expect(editButton).toHaveClass('pf-m-primary')
    await user.click(screen.getByRole('button', { name: 'User actions' }))
    expect(screen.getByRole('menuitem', { name: 'Revoke tokens' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Delete user' })).toBeInTheDocument()
  })

  it('hides the kebab menu when showKebabMenu is false', () => {
    render(
      <UserDetailToolbar
        permissions={fullPermissions}
        showKebabMenu={false}
        onEdit={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Edit user' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'User actions' })).not.toBeInTheDocument()
  })

  it('marks Edit user as aria-disabled when canUpdate is false', () => {
    render(
      <UserDetailToolbar
        permissions={{ ...fullPermissions, canUpdate: false }}
        showKebabMenu
        onEdit={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Edit user' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('calls onEdit when Edit user is clicked with update permission', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()

    render(
      <UserDetailToolbar
        permissions={fullPermissions}
        showKebabMenu
        onEdit={onEdit}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Edit user' }))
    expect(onEdit).toHaveBeenCalledOnce()
  })

  it('calls onRevoke and onDelete from kebab menu when permitted', async () => {
    const user = userEvent.setup()
    const onRevoke = vi.fn()
    const onDelete = vi.fn()

    render(
      <UserDetailToolbar
        permissions={fullPermissions}
        showKebabMenu
        onEdit={vi.fn()}
        onRevoke={onRevoke}
        onDelete={onDelete}
      />
    )

    await user.click(screen.getByRole('button', { name: 'User actions' }))
    await user.click(screen.getByRole('menuitem', { name: 'Revoke tokens' }))
    expect(onRevoke).toHaveBeenCalledOnce()

    await user.click(screen.getByRole('button', { name: 'User actions' }))
    await user.click(screen.getByRole('menuitem', { name: 'Delete user' }))
    expect(onDelete).toHaveBeenCalledOnce()
  })

  it('marks kebab actions as aria-disabled when revoke and delete are denied', async () => {
    const user = userEvent.setup()

    render(
      <UserDetailToolbar
        permissions={{ ...fullPermissions, canRevoke: false, canDelete: false }}
        showKebabMenu
        onEdit={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'User actions' }))
    expect(screen.getByRole('menuitem', { name: 'Revoke tokens' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('menuitem', { name: 'Delete user' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <UserDetailToolbar
        permissions={fullPermissions}
        showKebabMenu
        onEdit={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('UserDetailConfirmationDialogs', () => {
  it('renders revoke and delete confirmation dialogs when open', () => {
    render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={buildDialogState(mockUser)}
        deleteDialog={buildDialogState(mockUser, false)}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(screen.getByText('Revoke user tokens?')).toBeInTheDocument()
    expect(screen.getByText('test-user')).toBeInTheDocument()
  })

  it('renders delete confirmation dialog when open', () => {
    render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={buildDialogState(mockUser, false)}
        deleteDialog={buildDialogState(mockUser)}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(screen.getByText('Delete user?')).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', { name: 'I understand this user will be permanently deleted.' })
    ).toBeInTheDocument()
  })

  it('returns null for built-in users', () => {
    const { container } = render(
      <UserDetailConfirmationDialogs
        user={{ ...mockUser, is_builtin: true }}
        revokeDialog={buildDialogState(mockUser)}
        deleteDialog={buildDialogState(mockUser)}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('calls onRevoke when revoke confirmation is confirmed', async () => {
    const user = userEvent.setup()
    const onRevoke = vi.fn()

    render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={buildDialogState(mockUser)}
        deleteDialog={buildDialogState(mockUser, false)}
        onRevoke={onRevoke}
        onDelete={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Revoke tokens' }))
    expect(onRevoke).toHaveBeenCalledOnce()
  })

  it('calls onDelete when delete confirmation is confirmed', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()

    render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={buildDialogState(mockUser, false)}
        deleteDialog={buildDialogState(mockUser)}
        onRevoke={vi.fn()}
        onDelete={onDelete}
      />
    )

    await user.click(screen.getByRole('checkbox', { name: 'I understand this user will be permanently deleted.' }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onDelete).toHaveBeenCalledOnce()
  })

  it('calls revokeDialog.close when revoke confirmation is cancelled', async () => {
    const user = userEvent.setup()
    const revokeDialog = buildDialogState(mockUser)

    render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={revokeDialog}
        deleteDialog={buildDialogState(mockUser, false)}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(revokeDialog.close).toHaveBeenCalledOnce()
  })

  it('calls deleteDialog.close when delete confirmation is cancelled', async () => {
    const user = userEvent.setup()
    const deleteDialog = buildDialogState(mockUser)

    render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={buildDialogState(mockUser, false)}
        deleteDialog={deleteDialog}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(deleteDialog.close).toHaveBeenCalledOnce()
  })

  it('has no accessibility violations when revoke dialog is open', async () => {
    const { container } = render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={buildDialogState(mockUser)}
        deleteDialog={buildDialogState(mockUser, false)}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when delete dialog is open', async () => {
    const { container } = render(
      <UserDetailConfirmationDialogs
        user={mockUser}
        revokeDialog={buildDialogState(mockUser, false)}
        deleteDialog={buildDialogState(mockUser)}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
