import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import {
  KebabMenuViewsGroup,
  DuplicateMenuItem,
  ImportMenuItem,
  UnpublishMenuItem,
  DeleteMenuItem,
  KebabMenuActionsGroup,
} from './kebabMenuItems'

describe('KebabMenuViewsGroup', () => {
  it('renders workflow details for all workflow types', () => {
    render(
      <KebabMenuViewsGroup
        showExistingWorkflowItems={false}
        handleToggleHistory={vi.fn()}
        handleToggleVersionHistory={vi.fn()}
        handleToggleDetails={vi.fn()}
        closeKebab={vi.fn()}
      />
    )

    expect(screen.getByRole('menuitem', { name: /Workflow details/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Run history/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Version history/i })).not.toBeInTheDocument()
  })

  it('renders run and version history for existing workflows', () => {
    render(
      <KebabMenuViewsGroup
        showExistingWorkflowItems
        handleToggleHistory={vi.fn()}
        handleToggleVersionHistory={vi.fn()}
        handleToggleDetails={vi.fn()}
        closeKebab={vi.fn()}
      />
    )

    expect(screen.getByRole('menuitem', { name: /Run history/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Version history/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Workflow details/i })).toBeInTheDocument()
  })

  it('calls handlers and closes kebab when items clicked', async () => {
    const user = userEvent.setup()
    const handleToggleHistory = vi.fn()
    const handleToggleVersionHistory = vi.fn()
    const handleToggleDetails = vi.fn()
    const closeKebab = vi.fn()

    render(
      <KebabMenuViewsGroup
        showExistingWorkflowItems
        handleToggleHistory={handleToggleHistory}
        handleToggleVersionHistory={handleToggleVersionHistory}
        handleToggleDetails={handleToggleDetails}
        closeKebab={closeKebab}
      />
    )

    await user.click(screen.getByRole('menuitem', { name: /Run history/i }))
    expect(handleToggleHistory).toHaveBeenCalledTimes(1)
    expect(closeKebab).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('menuitem', { name: /Version history/i }))
    expect(handleToggleVersionHistory).toHaveBeenCalledTimes(1)
    expect(closeKebab).toHaveBeenCalledTimes(2)

    await user.click(screen.getByRole('menuitem', { name: /Workflow details/i }))
    expect(handleToggleDetails).toHaveBeenCalledTimes(1)
    expect(closeKebab).toHaveBeenCalledTimes(3)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <KebabMenuViewsGroup
        showExistingWorkflowItems
        handleToggleHistory={vi.fn()}
        handleToggleVersionHistory={vi.fn()}
        handleToggleDetails={vi.fn()}
        closeKebab={vi.fn()}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('DuplicateMenuItem', () => {
  it('renders duplicate menu item when enabled', () => {
    render(
      <DuplicateMenuItem canDuplicate duplicateTooltip="No permission" handleDuplicate={vi.fn()} closeKebab={vi.fn()} />
    )

    const item = screen.getByRole('menuitem', { name: /Duplicate workflow/i })
    expect(item).toBeInTheDocument()
    expect(item).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('disables duplicate when canDuplicate is false', () => {
    render(
      <DuplicateMenuItem
        canDuplicate={false}
        duplicateTooltip="No permission"
        handleDuplicate={vi.fn()}
        closeKebab={vi.fn()}
      />
    )

    expect(screen.getByRole('menuitem', { name: /Duplicate workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('calls handlers when enabled and clicked', async () => {
    const user = userEvent.setup()
    const handleDuplicate = vi.fn()
    const closeKebab = vi.fn()

    render(
      <DuplicateMenuItem
        canDuplicate
        duplicateTooltip="No permission"
        handleDuplicate={handleDuplicate}
        closeKebab={closeKebab}
      />
    )

    await user.click(screen.getByRole('menuitem', { name: /Duplicate workflow/i }))

    expect(handleDuplicate).toHaveBeenCalledTimes(1)
    expect(closeKebab).toHaveBeenCalledTimes(1)
  })

  it('does not call handlers when disabled', async () => {
    const user = userEvent.setup()
    const handleDuplicate = vi.fn()
    const closeKebab = vi.fn()

    render(
      <DuplicateMenuItem
        canDuplicate={false}
        duplicateTooltip="No permission"
        handleDuplicate={handleDuplicate}
        closeKebab={closeKebab}
      />
    )

    await user.click(screen.getByRole('menuitem', { name: /Duplicate workflow/i }))

    expect(handleDuplicate).not.toHaveBeenCalled()
    expect(closeKebab).not.toHaveBeenCalled()
  })

  it('shows tooltip when disabled', async () => {
    const user = userEvent.setup()

    render(
      <DuplicateMenuItem
        canDuplicate={false}
        duplicateTooltip="No create permission"
        handleDuplicate={vi.fn()}
        closeKebab={vi.fn()}
      />
    )

    await user.hover(screen.getByRole('menuitem', { name: /Duplicate workflow/i }))

    expect(await screen.findByText('No create permission')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <div role="menu">
        <DuplicateMenuItem
          canDuplicate
          duplicateTooltip="No permission"
          handleDuplicate={vi.fn()}
          closeKebab={vi.fn()}
        />
      </div>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('ImportMenuItem', () => {
  it('renders import menu item', () => {
    const ref = { current: null }
    render(<ImportMenuItem canEdit editTooltip="No permission" importFileRef={ref} closeKebab={vi.fn()} />)

    expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toBeInTheDocument()
  })

  it('disables import when canEdit is false', () => {
    const ref = { current: null }
    render(<ImportMenuItem canEdit={false} editTooltip="No permission" importFileRef={ref} closeKebab={vi.fn()} />)

    expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('triggers file input click when enabled', async () => {
    const user = userEvent.setup()
    const mockClick = vi.fn()
    const ref = { current: { click: mockClick } as unknown as HTMLInputElement }
    const closeKebab = vi.fn()

    render(<ImportMenuItem canEdit editTooltip="No permission" importFileRef={ref} closeKebab={closeKebab} />)

    await user.click(screen.getByRole('menuitem', { name: /Import workflow/i }))

    expect(mockClick).toHaveBeenCalledTimes(1)
    expect(closeKebab).toHaveBeenCalledTimes(1)
  })

  it('has no accessibility violations', async () => {
    const ref = { current: null }
    const { container } = render(
      <div role="menu">
        <ImportMenuItem canEdit editTooltip="No permission" importFileRef={ref} closeKebab={vi.fn()} />
      </div>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('UnpublishMenuItem', () => {
  it('renders unpublish menu item', () => {
    render(<UnpublishMenuItem canEdit unpublishTooltip="No permission" onUnpublish={vi.fn()} closeKebab={vi.fn()} />)

    expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toBeInTheDocument()
  })

  it('disables unpublish when canEdit is false', () => {
    render(
      <UnpublishMenuItem canEdit={false} unpublishTooltip="No permission" onUnpublish={vi.fn()} closeKebab={vi.fn()} />
    )

    expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('calls handlers when clicked', async () => {
    const user = userEvent.setup()
    const onUnpublish = vi.fn()
    const closeKebab = vi.fn()

    render(
      <UnpublishMenuItem canEdit unpublishTooltip="No permission" onUnpublish={onUnpublish} closeKebab={closeKebab} />
    )

    await user.click(screen.getByRole('menuitem', { name: /Unpublish workflow/i }))

    expect(onUnpublish).toHaveBeenCalledTimes(1)
    expect(closeKebab).toHaveBeenCalledTimes(1)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <div role="menu">
        <UnpublishMenuItem canEdit unpublishTooltip="No permission" onUnpublish={vi.fn()} closeKebab={vi.fn()} />
      </div>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('DeleteMenuItem', () => {
  it('renders delete menu item', () => {
    render(<DeleteMenuItem canDelete deleteTooltip="No permission" dispatch={vi.fn()} closeKebab={vi.fn()} />)

    expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toBeInTheDocument()
  })

  it('disables delete when canDelete is false', () => {
    render(<DeleteMenuItem canDelete={false} deleteTooltip="No permission" dispatch={vi.fn()} closeKebab={vi.fn()} />)

    expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('dispatches delete dialog action when clicked', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()
    const closeKebab = vi.fn()

    render(<DeleteMenuItem canDelete deleteTooltip="No permission" dispatch={dispatch} closeKebab={closeKebab} />)

    await user.click(screen.getByRole('menuitem', { name: /Delete workflow/i }))

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_DELETE_DIALOG', payload: true })
    expect(closeKebab).toHaveBeenCalledTimes(1)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <div role="menu">
        <DeleteMenuItem canDelete deleteTooltip="No permission" dispatch={vi.fn()} closeKebab={vi.fn()} />
      </div>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('KebabMenuActionsGroup', () => {
  const defaultProps = {
    showExistingWorkflowItems: false,
    publishedVersionId: null as string | null,
    canEdit: true,
    canCreate: true,
    canDelete: true,
    tooltips: {
      edit: 'No edit',
      save: 'No save',
      publish: 'No publish',
      unpublish: 'No unpublish',
      run: 'No run',
      delete: 'No delete',
      create: 'No create',
    },
    handleVerify: vi.fn(),
    handleDuplicate: vi.fn(),
    handleExport: vi.fn(),
    importFileRef: { current: null },
    onUnpublish: vi.fn(),
    dispatch: vi.fn(),
    closeKebab: vi.fn(),
  }

  it('renders all basic actions for new workflows', () => {
    render(<KebabMenuActionsGroup {...defaultProps} />)

    expect(screen.getByRole('menuitem', { name: /Verify workflow/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Duplicate workflow/i })).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Export workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toBeInTheDocument()
  })

  it('renders duplicate for existing workflows', () => {
    render(<KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems />)

    expect(screen.getByRole('menuitem', { name: /Duplicate workflow/i })).toBeInTheDocument()
  })

  it('renders unpublish for published workflows', () => {
    render(<KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems publishedVersionId="ver-1" />)

    expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toBeInTheDocument()
  })

  it('renders delete for existing workflows', () => {
    render(<KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems />)

    expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toBeInTheDocument()
  })

  it('does not render unpublish when not published', () => {
    render(<KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems publishedVersionId={null} />)

    expect(screen.queryByRole('menuitem', { name: /Unpublish workflow/i })).not.toBeInTheDocument()
  })

  it('does not render delete for new workflows', () => {
    render(<KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems={false} />)

    expect(screen.queryByRole('menuitem', { name: /Delete workflow/i })).not.toBeInTheDocument()
  })

  it('calls verify handler', async () => {
    const user = userEvent.setup()
    const handleVerify = vi.fn()

    render(<KebabMenuActionsGroup {...defaultProps} handleVerify={handleVerify} />)

    await user.click(screen.getByRole('menuitem', { name: /Verify workflow/i }))

    expect(handleVerify).toHaveBeenCalledTimes(1)
  })

  it('calls export handler', async () => {
    const user = userEvent.setup()
    const handleExport = vi.fn()

    render(<KebabMenuActionsGroup {...defaultProps} handleExport={handleExport} />)

    await user.click(screen.getByRole('menuitem', { name: /Export workflow/i }))

    expect(handleExport).toHaveBeenCalledTimes(1)
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems publishedVersionId="ver-1" />
    )

    expect(await axe(container)).toHaveNoViolations()
  })

  it('does not call handlers when canCreate is false for duplicate', async () => {
    const user = userEvent.setup()
    const handleDuplicate = vi.fn()

    render(
      <KebabMenuActionsGroup
        {...defaultProps}
        showExistingWorkflowItems
        canCreate={false}
        handleDuplicate={handleDuplicate}
      />
    )

    const duplicateItem = screen.getByRole('menuitem', { name: /Duplicate workflow/i })
    await user.click(duplicateItem)

    expect(handleDuplicate).not.toHaveBeenCalled()
  })

  it('does not call handlers when canEdit is false for import', async () => {
    const user = userEvent.setup()
    const mockClick = vi.fn()
    const importFileRef = { current: { click: mockClick } as unknown as HTMLInputElement }

    render(<KebabMenuActionsGroup {...defaultProps} canEdit={false} importFileRef={importFileRef} />)

    const importItem = screen.getByRole('menuitem', { name: /Import workflow/i })
    await user.click(importItem)

    expect(mockClick).not.toHaveBeenCalled()
  })

  it('does not call handlers when canEdit is false for unpublish', async () => {
    const user = userEvent.setup()
    const onUnpublish = vi.fn()

    render(
      <KebabMenuActionsGroup
        {...defaultProps}
        showExistingWorkflowItems
        publishedVersionId="ver-1"
        canEdit={false}
        onUnpublish={onUnpublish}
      />
    )

    const unpublishItem = screen.getByRole('menuitem', { name: /Unpublish workflow/i })
    await user.click(unpublishItem)

    expect(onUnpublish).not.toHaveBeenCalled()
  })

  it('does not call handlers when canDelete is false for delete', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()

    render(<KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems canDelete={false} dispatch={dispatch} />)

    const deleteItem = screen.getByRole('menuitem', { name: /Delete workflow/i })
    await user.click(deleteItem)

    expect(dispatch).not.toHaveBeenCalled()
  })

  it('renders all items when showExistingWorkflowItems and publishedVersionId are set', () => {
    render(
      <KebabMenuActionsGroup
        {...defaultProps}
        showExistingWorkflowItems
        publishedVersionId="ver-1"
        canEdit
        canCreate
        canDelete
      />
    )

    expect(screen.getByRole('menuitem', { name: /Verify workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Duplicate workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Export workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Unpublish workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Delete workflow/i })).toBeInTheDocument()
  })

  it('renders correct subset when showExistingWorkflowItems is false and not published', () => {
    render(<KebabMenuActionsGroup {...defaultProps} showExistingWorkflowItems={false} publishedVersionId={null} />)

    expect(screen.getByRole('menuitem', { name: /Verify workflow/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Duplicate workflow/i })).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Export workflow/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Import workflow/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Unpublish workflow/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Delete workflow/i })).not.toBeInTheDocument()
  })

  it('shows tooltips for all disabled actions', async () => {
    const user = userEvent.setup()
    const tooltips = {
      edit: 'Cannot edit',
      save: 'Cannot save',
      publish: 'Cannot publish',
      unpublish: 'Cannot unpublish',
      run: 'Cannot run',
      delete: 'Cannot delete',
      create: 'Cannot create',
    }

    render(
      <KebabMenuActionsGroup
        {...defaultProps}
        showExistingWorkflowItems
        publishedVersionId="ver-1"
        canEdit={false}
        canCreate={false}
        canDelete={false}
        tooltips={tooltips}
      />
    )

    // Hover over duplicate to show tooltip
    const duplicateItem = screen.getByRole('menuitem', { name: /Duplicate workflow/i })
    await user.hover(duplicateItem)
    expect(await screen.findByText('Cannot create')).toBeInTheDocument()

    // Hover over import to show tooltip
    const importItem = screen.getByRole('menuitem', { name: /Import workflow/i })
    await user.hover(importItem)
    expect(await screen.findByText('Cannot edit')).toBeInTheDocument()

    // Hover over unpublish to show tooltip
    const unpublishItem = screen.getByRole('menuitem', { name: /Unpublish workflow/i })
    await user.hover(unpublishItem)
    expect(await screen.findByText('Cannot unpublish')).toBeInTheDocument()

    // Hover over delete to show tooltip
    const deleteItem = screen.getByRole('menuitem', { name: /Delete workflow/i })
    await user.hover(deleteItem)
    expect(await screen.findByText('Cannot delete')).toBeInTheDocument()
  })
})
