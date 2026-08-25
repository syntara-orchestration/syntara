import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { KebabAction } from './SynKebabMenu'
import { SynKebabMenu } from './SynKebabMenu'

function buildActions(overrides: Partial<KebabAction>[] = []): KebabAction[] {
  const defaults: KebabAction[] = [
    { key: 'edit', title: 'Edit', onClick: vi.fn() },
    { key: 'sep', isSeparator: true },
    { key: 'delete', title: 'Delete', isDanger: true, onClick: vi.fn() },
  ]
  return defaults.map((action, i) => ({ ...action, ...overrides[i] }))
}

describe('SynKebabMenu', () => {
  it('renders a toggle button with the provided aria-label', () => {
    render(<SynKebabMenu actions={buildActions()} aria-label="Actions for item A" />)

    expect(screen.getByRole('button', { name: 'Actions for item A' })).toBeInTheDocument()
  })

  it('opens the menu and shows items when toggled', async () => {
    const user = userEvent.setup()
    render(<SynKebabMenu actions={buildActions()} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))

    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
  })

  it('renders separators between action groups', async () => {
    const user = userEvent.setup()
    render(<SynKebabMenu actions={buildActions()} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))

    expect(screen.getByRole('separator')).toBeInTheDocument()
  })

  it('calls onClick for enabled items', async () => {
    const user = userEvent.setup()
    const actions = buildActions()
    render(<SynKebabMenu actions={actions} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }))

    expect(actions[0].onClick).toHaveBeenCalledOnce()
  })

  it('does not call onClick and keeps menu open for aria-disabled items', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    const actions: KebabAction[] = [
      {
        key: 'edit',
        title: 'Edit',
        onClick,
        isAriaDisabled: true,
        tooltipProps: { content: 'No permission' },
      },
    ]
    render(<SynKebabMenu actions={actions} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }))

    expect(onClick).not.toHaveBeenCalled()
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
  })

  it('removes danger styling from aria-disabled items', async () => {
    const user = userEvent.setup()
    const actions: KebabAction[] = [
      { key: 'delete', title: 'Delete', isDanger: true, isAriaDisabled: true, onClick: vi.fn() },
    ]
    render(<SynKebabMenu actions={actions} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))

    const menu = screen.getByRole('menu')
    const item = within(menu).getByRole('menuitem', { name: 'Delete' })
    expect(item).not.toHaveClass('pf-m-danger')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<SynKebabMenu actions={buildActions()} aria-label="Row actions" />)

    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations when open', async () => {
    const user = userEvent.setup()
    const { container } = render(<SynKebabMenu actions={buildActions()} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))

    expect(await axe(container)).toHaveNoViolations()
  })

  it('does not invoke onClick for aria-disabled actions', async () => {
    const user = userEvent.setup()
    const onDisabledClick = vi.fn()
    const actions: KebabAction[] = [
      { key: 'disabled-action', title: 'Cannot do this', isAriaDisabled: true, onClick: onDisabledClick },
      { key: 'normal', title: 'Normal action', onClick: vi.fn() },
    ]
    render(<SynKebabMenu actions={actions} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))
    await user.click(screen.getByRole('menuitem', { name: 'Cannot do this' }))

    expect(onDisabledClick).not.toHaveBeenCalled()
  })

  it('schedules toggle blur via requestAnimationFrame after item click', async () => {
    const user = userEvent.setup()
    const rafSpy = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      cb(0)
      return 0
    })

    render(<SynKebabMenu actions={buildActions()} aria-label="Row actions" />)

    await user.click(screen.getByRole('button', { name: 'Row actions' }))
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }))

    expect(rafSpy).toHaveBeenCalled()
    rafSpy.mockRestore()
  })

  it('closes the previously open menu when another kebab is opened', async () => {
    const user = userEvent.setup()
    render(
      <>
        {/* stopPropagation mirrors Run History row wrappers that can block PF outside-click close */}
        <div onClick={(e) => e.stopPropagation()} role="presentation">
          <SynKebabMenu actions={buildActions()} aria-label="Actions for run A" />
        </div>
        <div onClick={(e) => e.stopPropagation()} role="presentation">
          <SynKebabMenu actions={buildActions()} aria-label="Actions for run B" />
        </div>
      </>
    )

    await user.click(screen.getByRole('button', { name: 'Actions for run A' }))
    expect(screen.getByRole('button', { name: 'Actions for run A', expanded: true })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Actions for run B' }))

    const expandedToggles = screen.getAllByRole('button', { expanded: true })
    expect(expandedToggles).toHaveLength(1)
    expect(expandedToggles[0]).toHaveAccessibleName('Actions for run B')
  })

  it('handles stable re-render without prop changes', () => {
    const actions = buildActions()
    const { rerender } = render(<SynKebabMenu actions={actions} aria-label="Row actions" />)
    rerender(<SynKebabMenu actions={actions} aria-label="Row actions" />)
    expect(screen.getByRole('button', { name: 'Row actions' })).toBeInTheDocument()
  })
})
