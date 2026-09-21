import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { CommandPalette } from './CommandPalette'
import { COMMAND_PALETTE_CATEGORY, type CommandPaletteItem } from './commandPaletteTypes'

const mockRequestNavigation = vi.fn()
const mockUseCommandPaletteItems = vi.fn<() => { items: CommandPaletteItem[]; isLoading: boolean }>()

vi.mock('../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({ requestNavigation: mockRequestNavigation }),
}))

vi.mock('./useCommandPaletteItems', () => ({
  useCommandPaletteItems: () => mockUseCommandPaletteItems(),
}))

const items: CommandPaletteItem[] = [
  {
    id: 'page:workflows',
    category: COMMAND_PALETTE_CATEGORY.PAGE,
    categoryLabel: 'Pages',
    title: 'Workflows',
    to: '/workflows',
    showWhenEmpty: true,
  },
  {
    id: 'workflow:wf-1',
    category: COMMAND_PALETTE_CATEGORY.WORKFLOW,
    categoryLabel: 'Workflows',
    title: 'Deploy app',
    subtitle: 'Production deploy',
    to: '/workflow-builder/wf-1',
  },
  {
    id: 'node:action',
    category: COMMAND_PALETTE_CATEGORY.NODE,
    categoryLabel: 'Steps',
    title: 'Action',
    keywords: ['http'],
    to: '/workflow-builder/new',
    showWhenEmpty: true,
  },
]

function renderPalette() {
  mockUseCommandPaletteItems.mockReturnValue({ items, isLoading: false })
  return render(<CommandPalette isOpen onClose={vi.fn()} />)
}

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('has no accessibility violations when open', async () => {
    const { container } = renderPalette()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('lists pages and steps before the user types', () => {
    renderPalette()

    expect(screen.getByRole('textbox', { name: /Search pages/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Pages: Workflows' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Steps: Action' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Workflows: Deploy app' })).not.toBeInTheDocument()
  })

  it('finds a workflow after typing', async () => {
    const user = userEvent.setup()
    renderPalette()

    await user.type(screen.getByRole('textbox', { name: /Search pages/i }), 'deploy')

    expect(screen.getByRole('option', { name: 'Workflows: Deploy app' })).toBeInTheDocument()
  })

  it('navigates and closes when a result is chosen', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockUseCommandPaletteItems.mockReturnValue({ items, isLoading: false })
    render(<CommandPalette isOpen onClose={onClose} />)

    await user.click(screen.getByRole('option', { name: 'Pages: Workflows' }))

    expect(onClose).toHaveBeenCalled()
    expect(mockRequestNavigation).toHaveBeenCalledWith('/workflows')
  })

  it('navigates the focused result with Enter', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockUseCommandPaletteItems.mockReturnValue({ items, isLoading: false })
    render(<CommandPalette isOpen onClose={onClose} />)

    const search = screen.getByRole('textbox', { name: /Search pages/i })
    search.focus()
    await user.keyboard('{ArrowDown}{Enter}')

    expect(mockRequestNavigation).toHaveBeenCalledWith('/workflow-builder/new')
    expect(onClose).toHaveBeenCalled()
  })

  it('shows an empty state when nothing matches', async () => {
    const user = userEvent.setup()
    renderPalette()

    await user.type(screen.getByRole('textbox', { name: /Search pages/i }), 'qwertyuiopasdfgh')

    expect(screen.getByText('No results found')).toBeInTheDocument()
  })

  it('shows a loading spinner when a query is pending remote results', async () => {
    const user = userEvent.setup()
    mockUseCommandPaletteItems.mockReturnValue({ items: [], isLoading: true })
    render(<CommandPalette isOpen onClose={vi.fn()} />)

    await user.type(screen.getByRole('textbox', { name: /Search pages/i }), 'deploy')

    expect(screen.getByLabelText('Loading search results')).toBeInTheDocument()
  })
})
