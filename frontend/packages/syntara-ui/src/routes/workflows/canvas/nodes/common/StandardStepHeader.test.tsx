import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

const mockNodesConnectable = vi.hoisted(() => ({ value: true }))

vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual('@xyflow/react')
  return {
    ...actual,
    useStore: (selector: (s: { nodesConnectable: boolean }) => boolean) =>
      selector({ nodesConnectable: mockNodesConnectable.value }),
  }
})

import { StandardStepHeader } from './StandardStepHeader'

describe('StandardStepHeader', () => {
  it('renders title and subtitle', () => {
    render(<StandardStepHeader title="Test Node" subtitle="Task" />)

    expect(screen.getByText('Test Node')).toBeInTheDocument()
    expect(screen.getByText('Task')).toBeInTheDocument()
  })

  it('renders icon when provided', () => {
    const icon = <svg data-testid="test-icon" />
    render(<StandardStepHeader title="Test Node" subtitle="Task" icon={icon} />)

    expect(screen.getByTestId('test-icon')).toBeInTheDocument()
  })

  it('does not render menu when no menuActions provided', () => {
    render(<StandardStepHeader title="Test Node" subtitle="Task" />)

    expect(screen.queryByRole('button', { name: /step actions menu/i })).not.toBeInTheDocument()
  })

  it('does not render menu when menuActions is empty', () => {
    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={[]} />)

    expect(screen.queryByRole('button', { name: /step actions menu/i })).not.toBeInTheDocument()
  })

  it('renders kebab menu button when menuActions provided', () => {
    const menuActions = [{ id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const }]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    expect(screen.getByRole('button', { name: /step actions menu/i })).toBeInTheDocument()
  })

  it('opens menu dropdown when kebab button is clicked', async () => {
    const user = userEvent.setup()
    const menuActions = [{ id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const }]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })
  })

  it('calls onClick handler when menu item is clicked', async () => {
    const user = userEvent.setup()
    const deleteHandler = vi.fn()
    const menuActions = [{ id: 'delete', label: 'Delete', onClick: deleteHandler, variant: 'danger' as const }]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    // Open menu
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    // Click delete option
    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('menuitem', { name: 'Delete' }))

    expect(deleteHandler).toHaveBeenCalledTimes(1)
  })

  it('renders multiple menu items', async () => {
    const user = userEvent.setup()
    const menuActions = [
      { id: 'edit', label: 'Edit', onClick: vi.fn() },
      { id: 'duplicate', label: 'Duplicate', onClick: vi.fn() },
      { id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const },
    ]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    // Open menu
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Duplicate' })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })
  })

  it('renders menu separator correctly', async () => {
    const user = userEvent.setup()
    const menuActions = [
      { id: 'edit', label: 'Edit', onClick: vi.fn() },
      { id: 'separator', label: '', onClick: vi.fn(), separator: true },
      { id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const },
    ]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    // Open menu
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    })

    // There should be a separator between the menu items
    const separator = screen.getByRole('separator')
    expect(separator).toBeInTheDocument()
  })

  it('renders icon in menu item when provided', async () => {
    const user = userEvent.setup()
    const icon = <svg data-testid="action-icon" />
    const menuActions = [{ id: 'delete', label: 'Delete', onClick: vi.fn(), icon }]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    // Open menu
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    await waitFor(() => {
      expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
      expect(screen.getByTestId('action-icon')).toBeInTheDocument()
    })
  })

  it('applies danger styling to danger variant menu items', async () => {
    const user = userEvent.setup()
    const menuActions = [{ id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const }]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    // Open menu
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    await waitFor(() => {
      expect(screen.getByTestId('node-menu-item-delete')).toHaveClass('pf-m-danger')
    })
  })

  it('hides menu when nodesConnectable is false', () => {
    mockNodesConnectable.value = false
    const menuActions = [{ id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' as const }]

    render(<StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />)

    expect(screen.queryByRole('button', { name: /step actions menu/i })).not.toBeInTheDocument()
    mockNodesConnectable.value = true
  })

  it('prevents event propagation from menu trigger', async () => {
    const user = userEvent.setup()
    const parentClickHandler = vi.fn()
    const menuActions = [{ id: 'delete', label: 'Delete', onClick: vi.fn() }]

    render(
      // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
      <div onClick={parentClickHandler}>
        <StandardStepHeader title="Test Node" subtitle="Task" menuActions={menuActions} />
      </div>
    )

    // Click menu button
    const menuButton = screen.getByRole('button', { name: /step actions menu/i })
    await user.click(menuButton)

    // Parent click handler should not be called (due to stopPropagation)
    expect(parentClickHandler).not.toHaveBeenCalled()
  })
})
