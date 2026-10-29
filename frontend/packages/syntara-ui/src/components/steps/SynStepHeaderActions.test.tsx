import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynStepExpandedContext } from './SynStepExpandedContext'
import { SynStepHeaderActions } from './SynStepHeaderActions'

describe('SynStepHeaderActions', () => {
  it('returns null when there are no header actions to show', () => {
    const { container } = render(
      <SynStepHeaderActions stepTitle="Deploy" showMenuActions={false} menuActions={[]} expandable={false} />
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('renders expand toggle before edit and kebab when all are available', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    const menuActions = [
      { id: 'view-details', label: 'View step details', onClick: onEdit },
      { id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const },
    ]

    render(
      <SynStepExpandedContext.Provider value={[true, vi.fn()]}>
        <SynStepHeaderActions
          stepTitle="Deploy"
          showMenuActions
          menuActions={menuActions}
          expandable
        />
      </SynStepExpandedContext.Provider>
    )

    expect(screen.getByRole('button', { name: 'Collapse details for Deploy' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Edit Deploy' }))
    expect(onEdit).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: /step actions menu/i }))
    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })
    expect(screen.queryByRole('menuitem', { name: 'View step details' })).not.toBeInTheDocument()
  })

  it('renders kebab without edit when view-details is absent', async () => {
    const user = userEvent.setup()
    render(
      <SynStepHeaderActions
        stepTitle="Deploy"
        showMenuActions
        menuActions={[{ id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const }]}
      />
    )

    await user.click(screen.getByRole('button', { name: /step actions menu/i }))
    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: 'Edit Deploy' })).not.toBeInTheDocument()
  })

  it('has no axe violations', async () => {
    const { container } = render(
      <SynStepExpandedContext.Provider value={[true, vi.fn()]}>
        <SynStepHeaderActions
          stepTitle="Deploy"
          showMenuActions
          expandable
          menuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]}
        />
      </SynStepExpandedContext.Provider>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
