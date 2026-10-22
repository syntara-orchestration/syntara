import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { usePendingBuilderNodeAddStore } from '../../routes/builder/pendingBuilderNodeAddStore'
import { routerTestState } from '../../test/setup'

import { CommandPalette } from './CommandPalette'
import { commandPaletteOptionId } from './commandPaletteDom'
import { COMMAND_PALETTE_CATEGORY, type CommandPaletteItem } from './commandPaletteTypes'

const mockRequestNavigation = vi.fn()
const mockShowError = vi.fn()
const mockUseCommandPaletteItems =
  vi.fn<() => { items: CommandPaletteItem[]; isLoading: boolean; error: unknown; refetch: () => void }>()

vi.mock('../../app/useUnsavedChanges', () => ({
  useUnsavedChanges: () => ({ requestNavigation: mockRequestNavigation }),
}))

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mockShowError }),
}))

vi.mock('./useCommandPaletteItems', () => ({
  useCommandPaletteItems: () => mockUseCommandPaletteItems(),
}))

const items: CommandPaletteItem[] = [
  {
    id: 'page:workflows',
    category: COMMAND_PALETTE_CATEGORY.PAGE,
    categoryLabel: 'Page',
    title: 'Workflows',
    to: '/workflows',
    showWhenEmpty: true,
  },
  {
    id: 'workflow:wf-1',
    category: COMMAND_PALETTE_CATEGORY.WORKFLOW,
    categoryLabel: 'Workflow',
    title: 'Deploy app',
    subtitle: 'Production deploy',
    to: '/workflow-builder/wf-1',
  },
  {
    id: 'node:action',
    category: COMMAND_PALETTE_CATEGORY.NODE,
    categoryLabel: 'Step',
    title: 'Action',
    keywords: ['http'],
    to: '/workflow-builder/new',
    builderAdd: { nodeTypeId: 'action', nodeSubtypeId: null },
    showWhenEmpty: true,
  },
  {
    id: 'node:trigger:trigger-manual',
    category: COMMAND_PALETTE_CATEGORY.NODE,
    categoryLabel: 'Step',
    title: 'Manual trigger',
    to: '/workflow-builder/new',
    builderAdd: { nodeTypeId: 'trigger', nodeSubtypeId: 'trigger-manual' },
    showWhenEmpty: true,
  },
]

function catalog(overrides: Partial<{ items: CommandPaletteItem[]; isLoading: boolean; error: unknown }> = {}) {
  return { items, isLoading: false, error: null, refetch: vi.fn(), ...overrides }
}

function renderPalette() {
  mockUseCommandPaletteItems.mockReturnValue(catalog())
  return render(<CommandPalette isOpen onClose={vi.fn()} />)
}

function searchField() {
  return screen.getByRole('combobox', { name: /Search pages/i })
}

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    usePendingBuilderNodeAddStore.getState().clear()
  })

  it('has no accessibility violations when open', async () => {
    const { container } = renderPalette()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('lists pages and steps before the user types', () => {
    renderPalette()

    expect(searchField()).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Page: Workflows' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Step: Action' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Workflow: Deploy app' })).not.toBeInTheDocument()
  })

  it('finds a workflow after typing', async () => {
    const user = userEvent.setup()
    renderPalette()

    await user.type(searchField(), 'deploy')

    expect(screen.getByRole('option', { name: 'Workflow: Deploy app' })).toBeInTheDocument()
  })

  it('navigates and closes when a result is chosen', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockUseCommandPaletteItems.mockReturnValue(catalog())
    render(<CommandPalette isOpen onClose={onClose} />)

    await user.click(screen.getByRole('option', { name: 'Page: Workflows' }))

    expect(onClose).toHaveBeenCalled()
    expect(mockRequestNavigation).toHaveBeenCalledWith('/workflows')
  })

  it('does not activate a result on Enter until the user highlights one', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockUseCommandPaletteItems.mockReturnValue(catalog())
    render(<CommandPalette isOpen onClose={onClose} />)

    searchField().focus()
    await user.keyboard('{Enter}')

    expect(onClose).not.toHaveBeenCalled()
    expect(mockRequestNavigation).not.toHaveBeenCalled()
  })

  it('navigates the focused result with Enter', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    mockUseCommandPaletteItems.mockReturnValue(catalog())
    render(<CommandPalette isOpen onClose={onClose} />)

    searchField().focus()
    await user.keyboard('{ArrowDown}')

    expect(searchField()).toHaveAttribute('aria-activedescendant', commandPaletteOptionId('page:workflows'))
    expect(screen.getByRole('option', { name: 'Page: Workflows' })).toHaveAttribute('aria-selected', 'true')

    await user.keyboard('{Enter}')

    expect(mockRequestNavigation).toHaveBeenCalledWith('/workflows')
    expect(onClose).toHaveBeenCalled()
  })

  it('adds a step to the open workflow instead of creating a new one', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    routerTestState.pathname = '/workflow-builder/wf-1'
    mockUseCommandPaletteItems.mockReturnValue(catalog())
    render(<CommandPalette isOpen onClose={onClose} />)

    await user.click(screen.getByRole('option', { name: 'Step: Manual trigger' }))

    expect(onClose).toHaveBeenCalled()
    expect(mockRequestNavigation).not.toHaveBeenCalled()
    expect(usePendingBuilderNodeAddStore.getState().pending).toEqual({
      nodeTypeId: 'trigger',
      nodeSubtypeId: 'trigger-manual',
    })
  })

  it('explains when a step cannot be added on a read-only builder', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    routerTestState.pathname = '/workflow-builder/wf-1'
    usePendingBuilderNodeAddStore.getState().setCanAcceptStepAdd(false)
    mockUseCommandPaletteItems.mockReturnValue(catalog())
    render(<CommandPalette isOpen onClose={onClose} />)

    await user.click(screen.getByRole('option', { name: 'Step: Manual trigger' }))

    expect(onClose).not.toHaveBeenCalled()
    expect(mockShowError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Cannot add a step' }))
    expect(usePendingBuilderNodeAddStore.getState().pending).toBeNull()
  })

  it('shows an empty state when nothing matches', async () => {
    const user = userEvent.setup()
    renderPalette()

    await user.type(searchField(), 'qwertyuiopasdfgh')

    expect(screen.getByRole('heading', { name: 'No results found' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('No results found')
  })

  it('shows a loading spinner when a query is pending remote results', async () => {
    const user = userEvent.setup()
    mockUseCommandPaletteItems.mockReturnValue(catalog({ items: [], isLoading: true }))
    render(<CommandPalette isOpen onClose={vi.fn()} />)

    await user.type(searchField(), 'deploy')

    expect(screen.getByLabelText('Loading search results')).toBeInTheDocument()
  })

  it('distinguishes catalog errors from empty results', async () => {
    const user = userEvent.setup()
    const refetch = vi.fn()
    mockUseCommandPaletteItems.mockReturnValue({ items: [], isLoading: false, error: new Error('boom'), refetch })
    render(<CommandPalette isOpen onClose={vi.fn()} />)

    await user.type(searchField(), 'deploy')

    expect(screen.getByText('Search sources could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })
})
