import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ProjectDeleteDialog } from './ProjectDeleteDialog'

describe('ProjectDeleteDialog', () => {
  it('has no accessibility violations when open', async () => {
    const { baseElement } = render(
      <ProjectDeleteDialog isOpen projectName="My Project" onClose={vi.fn()} onConfirm={vi.fn()} />
    )

    expect(await axe(baseElement)).toHaveNoViolations()
  })

  it('renders project name and cascade consequence list', () => {
    render(<ProjectDeleteDialog isOpen projectName="My Project" onClose={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText('Delete project?')).toBeInTheDocument()
    expect(screen.getByText('My Project')).toBeInTheDocument()
    expect(screen.getByText(/will be deleted\. This cannot be undone\./)).toBeInTheDocument()
    expect(screen.getByText('Resources that will be deleted:')).toBeInTheDocument()
    expect(screen.getByText('Workflows, executions, and approval requests')).toBeInTheDocument()
    expect(screen.getByText('Credentials and service accounts')).toBeInTheDocument()
    expect(screen.getByText('Uploaded files')).toBeInTheDocument()
    expect(screen.getByText('Role assignments, project roles, and policies')).toBeInTheDocument()
    expect(screen.getByText('Integration assignments for this project')).toBeInTheDocument()
  })

  it('keeps Delete disabled until acknowledgement is checked, then calls onConfirm', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    render(<ProjectDeleteDialog isOpen projectName="My Project" onClose={onClose} onConfirm={onConfirm} />)

    const dialog = screen.getByRole('dialog')
    const deleteButton = within(dialog).getByRole('button', { name: 'Delete' })

    expect(deleteButton).toBeDisabled()

    await user.click(
      within(dialog).getByRole('checkbox', {
        name: /I understand this project and the resources listed above will be permanently deleted/,
      })
    )

    expect(deleteButton).toBeEnabled()
    await user.click(deleteButton)

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
  })
})
