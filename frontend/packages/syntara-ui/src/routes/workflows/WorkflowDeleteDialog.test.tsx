import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { WorkflowDeleteDialog } from './WorkflowDeleteDialog'

describe('WorkflowDeleteDialog', () => {
  it('has no accessibility violations when open', async () => {
    const { baseElement } = render(
      <WorkflowDeleteDialog isOpen workflowName="Deploy app" onClose={vi.fn()} onConfirm={vi.fn()} />
    )

    expect(await axe(baseElement)).toHaveNoViolations()
  })

  it('renders workflow name and simplified delete copy', () => {
    render(<WorkflowDeleteDialog isOpen workflowName="Deploy app" onClose={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
    expect(screen.getByText('Deploy app')).toBeInTheDocument()
    expect(
      screen.getByText(
        /will be deleted and any in-progress runs will stop immediately\. This action cannot be undone\./
      )
    ).toBeInTheDocument()
    expect(screen.queryByText(/dependent workflows|use this one as a step/)).not.toBeInTheDocument()
  })

  it('keeps Delete disabled until acknowledgement is checked, then calls onConfirm', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    render(<WorkflowDeleteDialog isOpen workflowName="Deploy app" onClose={onClose} onConfirm={onConfirm} />)

    const dialog = screen.getByRole('dialog')
    const deleteButton = within(dialog).getByRole('button', { name: 'Delete' })

    expect(deleteButton).toBeDisabled()

    await user.click(
      within(dialog).getByRole('checkbox', {
        name: /I understand this workflow will be deleted and any in-progress runs will stop immediately/,
      })
    )

    expect(deleteButton).toBeEnabled()
    await user.click(deleteButton)

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
  })
})
