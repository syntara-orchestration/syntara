import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReactFlowProvider } from '@xyflow/react'
import type { ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

const updateNodeInternals = vi.hoisted(() => vi.fn())
const executionViewState = vi.hoisted(() => ({ isExecutionView: false }))
const activeExecutionState = vi.hoisted(() => ({ isActiveExecution: false }))
const versionViewState = vi.hoisted(() => ({ isVersionView: false }))
const nodesConnectableState = vi.hoisted(() => ({ nodesConnectable: true }))

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return {
    ...actual,
    useNodeId: () => 'semantic-zoom-node',
    useUpdateNodeInternals: () => updateNodeInternals,
    useStore: (selector: (s: { nodesConnectable: boolean; transform: [number, number, number] }) => unknown) =>
      selector({ nodesConnectable: nodesConnectableState.nodesConnectable, transform: [0, 0, 0.5] }),
  }
})

vi.mock('../../routes/builder/ExecutionViewContext', () => ({
  useIsExecutionView: () => executionViewState.isExecutionView,
}))

vi.mock('../../routes/builder/ActiveExecutionContext', () => ({
  useIsActiveExecution: () => activeExecutionState.isActiveExecution,
}))

vi.mock('../../routes/builder/VersionViewContext', () => ({
  useIsVersionView: () => versionViewState.isVersionView,
}))

vi.mock('../../routes/workflows/canvas/nodes/common/SemanticZoomBranchSourceHandles', () => ({
  SemanticZoomBranchSourceHandles: () => null,
}))

import { SynStepSemanticZoomBody } from './SynStepSemanticZoomBody'

function renderWithFlow(ui: ReactElement) {
  return render(<ReactFlowProvider>{ui}</ReactFlowProvider>)
}

const baseProps = {
  title: 'Analyze Data',
  typeLabel: 'Task Agent',
  accentColor: 'rgb(100, 100, 200)',
  selected: false,
  hasDashedBorder: false,
}

describe('SynStepSemanticZoomBody', () => {
  afterEach(() => {
    executionViewState.isExecutionView = false
    activeExecutionState.isActiveExecution = false
    versionViewState.isVersionView = false
    nodesConnectableState.nodesConnectable = true
    updateNodeInternals.mockClear()
  })

  it('exposes title and type on the compact tile focus target', () => {
    renderWithFlow(<SynStepSemanticZoomBody {...baseProps} />)

    expect(screen.queryByRole('heading', { name: 'Analyze Data' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze Data, Task Agent' })).toBeInTheDocument()
  })

  it('renders semantic zoom icon slot when icon is provided', () => {
    renderWithFlow(<SynStepSemanticZoomBody {...baseProps} icon={<span data-testid="zoom-icon">icon</span>} />)
    expect(screen.getByTestId('zoom-icon')).toBeInTheDocument()
  })

  it('calls updateNodeInternals when branch source count changes', () => {
    const { rerender } = renderWithFlow(
      <SynStepSemanticZoomBody {...baseProps} branchSources={[{ id: 'true', ariaLabel: 'True branch output' }]} />
    )
    expect(updateNodeInternals).toHaveBeenCalledWith('semantic-zoom-node')

    updateNodeInternals.mockClear()
    rerender(
      <SynStepSemanticZoomBody
        {...baseProps}
        branchSources={[
          { id: 'true', ariaLabel: 'True branch output' },
          { id: 'false', ariaLabel: 'False branch output' },
        ]}
      />
    )
    expect(updateNodeInternals).toHaveBeenCalledWith('semantic-zoom-node')
  })

  it('shows full preview with edit and menu on hover', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderWithFlow(
      <SynStepSemanticZoomBody
        {...baseProps}
        menuActions={[
          { id: 'view-details', label: 'Edit', onClick: vi.fn() },
          { id: 'delete', label: 'Delete', onClick: vi.fn() },
        ]}
      />
    )

    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()

    await user.hover(screen.getByRole('button', { name: 'Analyze Data, Task Agent' }))

    expect(screen.getByRole('heading', { name: 'Analyze Data' })).toBeInTheDocument()
    expect(screen.getByText('Task Agent')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit Analyze Data' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Step actions menu' })).toBeInTheDocument()
  })

  it('shows full preview when compact tile receives keyboard focus', async () => {
    const user = userEvent.setup()
    renderWithFlow(
      <SynStepSemanticZoomBody {...baseProps} menuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]} />
    )

    await user.tab()
    await waitFor(() => {
      expect(screen.getByTestId('semantic-zoom-preview')).toBeVisible()
    })
    expect(screen.getByRole('heading', { name: 'Analyze Data' })).toBeInTheDocument()
  })

  it('hides actions in execution, active execution, or version view', async () => {
    const user = userEvent.setup()
    const menuActions = [{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]

    executionViewState.isExecutionView = true
    const { unmount } = renderWithFlow(<SynStepSemanticZoomBody {...baseProps} menuActions={menuActions} />)
    await user.hover(screen.getByRole('button', { name: 'Analyze Data, Task Agent' }))
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
    unmount()

    executionViewState.isExecutionView = false
    activeExecutionState.isActiveExecution = true
    const { unmount: unmount2 } = renderWithFlow(<SynStepSemanticZoomBody {...baseProps} menuActions={menuActions} />)
    await user.hover(screen.getByRole('button', { name: 'Analyze Data, Task Agent' }))
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
    unmount2()

    activeExecutionState.isActiveExecution = false
    versionViewState.isVersionView = true
    renderWithFlow(<SynStepSemanticZoomBody {...baseProps} menuActions={menuActions} />)
    await user.hover(screen.getByRole('button', { name: 'Analyze Data, Task Agent' }))
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
  })

  it('hides actions when nodes are not connectable', async () => {
    const user = userEvent.setup()
    nodesConnectableState.nodesConnectable = false
    renderWithFlow(
      <SynStepSemanticZoomBody {...baseProps} menuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]} />
    )
    await user.hover(screen.getByRole('button', { name: 'Analyze Data, Task Agent' }))
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
  })

  it('uses preview icon in the hover card when previewIcon is provided', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderWithFlow(
      <SynStepSemanticZoomBody
        {...baseProps}
        icon={<span data-testid="tile-icon">tile</span>}
        previewIcon={<span data-testid="preview-icon">preview</span>}
        menuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]}
      />
    )

    await user.hover(screen.getByRole('button', { name: 'Analyze Data, Task Agent' }))
    expect(screen.getByTestId('preview-icon')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderWithFlow(
      <SynStepSemanticZoomBody
        {...baseProps}
        icon={<span aria-hidden="true" />}
        menuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]}
        tileStyle={{ borderTopLeftRadius: '8px' }}
      />
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
