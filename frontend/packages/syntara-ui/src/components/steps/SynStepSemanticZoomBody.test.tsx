import { render, screen } from '@testing-library/react'
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
    useStore: (selector: (s: { nodesConnectable: boolean }) => unknown) =>
      selector({ nodesConnectable: nodesConnectableState.nodesConnectable }),
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

  it('exposes title and type on the tooltip trigger without on-canvas labels', () => {
    renderWithFlow(<SynStepSemanticZoomBody {...baseProps} />)

    expect(screen.queryByText('Analyze Data')).not.toBeInTheDocument()
    expect(screen.queryByText('Task Agent')).not.toBeInTheDocument()
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

  it('shows edit and menu actions when connectable and not in read-only views', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    renderWithFlow(
      <SynStepSemanticZoomBody
        {...baseProps}
        selected
        menuActions={[
          { id: 'view-details', label: 'Edit', onClick: onEdit },
          { id: 'delete', label: 'Delete', onClick: vi.fn() },
        ]}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Edit Analyze Data' }))
    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Step actions menu' })).toBeInTheDocument()
  })

  it('hides actions in execution, active execution, or version view', () => {
    const menuActions = [{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]

    executionViewState.isExecutionView = true
    const { unmount } = renderWithFlow(<SynStepSemanticZoomBody {...baseProps} menuActions={menuActions} />)
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
    unmount()

    executionViewState.isExecutionView = false
    activeExecutionState.isActiveExecution = true
    const { unmount: unmount2 } = renderWithFlow(<SynStepSemanticZoomBody {...baseProps} menuActions={menuActions} />)
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
    unmount2()

    activeExecutionState.isActiveExecution = false
    versionViewState.isVersionView = true
    renderWithFlow(<SynStepSemanticZoomBody {...baseProps} menuActions={menuActions} />)
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
  })

  it('hides actions when nodes are not connectable', () => {
    nodesConnectableState.nodesConnectable = false
    renderWithFlow(
      <SynStepSemanticZoomBody {...baseProps} menuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]} />
    )
    expect(screen.queryByRole('button', { name: 'Edit Analyze Data' })).not.toBeInTheDocument()
  })

  it('shows tooltip content on hover', async () => {
    const user = userEvent.setup()
    renderWithFlow(<SynStepSemanticZoomBody {...baseProps} />)

    await user.hover(screen.getByRole('button', { name: 'Analyze Data, Task Agent' }))

    expect(await screen.findByText('Analyze Data')).toBeInTheDocument()
    expect(screen.getByText('Task Agent')).toBeInTheDocument()
  })

  it('shows overlay actions when selected without hover', () => {
    renderWithFlow(
      <SynStepSemanticZoomBody
        {...baseProps}
        selected
        menuActions={[{ id: 'view-details', label: 'Edit', onClick: vi.fn() }]}
      />
    )
    expect(screen.getByRole('button', { name: 'Edit Analyze Data' })).toBeInTheDocument()
    expect(screen.getByTestId('semantic-zoom-actions')).toBeInTheDocument()
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
