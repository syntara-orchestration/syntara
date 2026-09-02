import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RegistryNodeId } from '../../../constants'

import type { UpstreamNodeInfo } from './hooks/useUpstreamNodes'
import { NodePanelNavigationArrow } from './NodePanelNavigationArrow'

function MockNavIcon() {
  return <svg data-testid="mock-nav-icon" />
}

const singleNode: UpstreamNodeInfo[] = [{ id: 'node-a', name: 'Create ServiceNOW Ticket', type: 'script' }]

const multipleNodes: UpstreamNodeInfo[] = [
  { id: 'node-a', name: 'Task A', type: 'script', icon: MockNavIcon, iconId: RegistryNodeId.ACTION_SCRIPT },
  { id: 'node-b', name: 'Task B', type: 'script', icon: MockNavIcon, iconId: RegistryNodeId.ACTION_SCRIPT },
]

describe('NodePanelNavigationArrow', () => {
  it('renders nothing when nodes array is empty', () => {
    const { container } = render(<NodePanelNavigationArrow direction="previous" nodes={[]} onNavigate={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('navigates directly when single upstream target is clicked', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()

    render(<NodePanelNavigationArrow direction="previous" nodes={singleNode} onNavigate={onNavigate} />)

    await user.click(screen.getByRole('button', { name: /Go to previous step: Create ServiceNOW Ticket/i }))

    expect(onNavigate).toHaveBeenCalledWith('node-a')
  })

  it('opens dropdown when multiple upstream targets are present', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()

    render(<NodePanelNavigationArrow direction="previous" nodes={multipleNodes} onNavigate={onNavigate} />)

    await user.click(screen.getByRole('button', { name: /Previous step/i }))
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await user.click(screen.getByRole('menuitem', { name: 'Task B' }))
    expect(onNavigate).toHaveBeenCalledWith('node-b')
  })

  it('uses next-step labeling for downstream direction', () => {
    render(<NodePanelNavigationArrow direction="next" nodes={multipleNodes} onNavigate={vi.fn()} />)

    expect(screen.getByRole('button', { name: /Next step/i })).toBeInTheDocument()
  })

  it('falls back to type label when single target name is empty', () => {
    const unnamed: UpstreamNodeInfo[] = [{ id: 'node-a', name: '', type: 'converge' }]

    render(<NodePanelNavigationArrow direction="previous" nodes={unnamed} onNavigate={vi.fn()} />)

    expect(screen.getByRole('button', { name: /Go to previous step: Converge/i })).toBeInTheDocument()
  })

  it('falls back to type labels in multi-target dropdown when names are empty', async () => {
    const user = userEvent.setup()
    const unnamed: UpstreamNodeInfo[] = [
      { id: 'node-a', name: '', type: 'script' },
      { id: 'node-b', name: '   ', type: 'wait' },
    ]

    render(<NodePanelNavigationArrow direction="previous" nodes={unnamed} onNavigate={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Previous step/i }))

    expect(screen.getByRole('menuitem', { name: 'Script' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Wait' })).toBeInTheDocument()
  })

  it('shows node type icons next to step names in the navigation dropdown', async () => {
    const user = userEvent.setup()

    render(<NodePanelNavigationArrow direction="next" nodes={multipleNodes} onNavigate={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Next step/i }))

    expect(screen.getByRole('menuitem', { name: 'Task A' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Task B' })).toBeInTheDocument()
    expect(screen.getAllByTestId('node-icon-wrapper')).toHaveLength(2)
    expect(screen.getAllByTestId('mock-nav-icon')).toHaveLength(2)
  })

  it('renders dropdown step names without icons when nodes have no icon or iconId', async () => {
    const user = userEvent.setup()
    const nodesWithoutIcons: UpstreamNodeInfo[] = [
      { id: 'node-a', name: 'Task A', type: 'script' },
      { id: 'node-b', name: 'Task B', type: 'wait' },
    ]

    render(<NodePanelNavigationArrow direction="previous" nodes={nodesWithoutIcons} onNavigate={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /Previous step/i }))

    expect(screen.getByRole('menuitem', { name: 'Task A' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Task B' })).toBeInTheDocument()
    expect(screen.queryByTestId('node-icon-wrapper')).not.toBeInTheDocument()
  })

  it('has no accessibility violations for single-target arrow', async () => {
    const { container } = render(
      <NodePanelNavigationArrow direction="previous" nodes={singleNode} onNavigate={vi.fn()} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations for multi-target arrow', async () => {
    const { container } = render(
      <NodePanelNavigationArrow direction="next" nodes={multipleNodes} onNavigate={vi.fn()} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
