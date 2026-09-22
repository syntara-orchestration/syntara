import { EdgeHandleEnum } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Node } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FlowNodeType } from '../../../constants/nodeTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import { RightSidePill } from './RightSidePill'

// Helper to create mock nodes
function createMockNode(type: string, data?: Partial<NodeType['data']>): Node<NodeType['data']> {
  return {
    id: 'test-node-1',
    type,
    position: { x: 0, y: 0 },
    data: data ?? { name: 'Test Node' },
  }
}

describe('RightSidePill', () => {
  describe('when onAddStep is not provided', () => {
    it('renders nothing', () => {
      const { container } = render(<RightSidePill node={createMockNode(FlowNodeType.TASK)} />)
      expect(container).toBeEmptyDOMElement()
    })
  })

  describe('non-branching nodes', () => {
    it('renders a plain button for task node', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.TASK)} onAddStep={onAddStep} />)

      const button = screen.getByRole('button', { name: 'Add step' })
      expect(button).toBeInTheDocument()

      await user.click(button)
      expect(onAddStep).toHaveBeenCalledWith()
      expect(onAddStep).toHaveBeenCalledTimes(1)
    })

    it('renders a plain button when node is undefined', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={undefined} onAddStep={onAddStep} />)

      const button = screen.getByRole('button', { name: 'Add step' })
      expect(button).toBeInTheDocument()

      await user.click(button)
      expect(onAddStep).toHaveBeenCalledWith()
    })

    it('renders a plain button for unrecognized node types', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode('unknown-node-type')} onAddStep={onAddStep} />)

      const button = screen.getByRole('button', { name: 'Add step' })
      expect(button).toBeInTheDocument()

      await user.click(button)
      expect(onAddStep).toHaveBeenCalledWith()
    })
  })

  describe('branching nodes - condition', () => {
    it('renders dropdown with true/false options for condition node', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      expect(toggle).toBeInTheDocument()

      await user.click(toggle)

      expect(screen.getByText('On True')).toBeInTheDocument()
      expect(screen.getByText('On False')).toBeInTheDocument()
    })

    it('calls onAddStep with "true" handle when "On True" is selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const onTrueOption = screen.getByText('On True')
      await user.click(onTrueOption)

      expect(onAddStep).toHaveBeenCalledWith(EdgeHandleEnum.TRUE)
      expect(onAddStep).toHaveBeenCalledTimes(1)
    })

    it('calls onAddStep with "false" handle when "On False" is selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const onFalseOption = screen.getByText('On False')
      await user.click(onFalseOption)

      expect(onAddStep).toHaveBeenCalledWith(EdgeHandleEnum.FALSE)
      expect(onAddStep).toHaveBeenCalledTimes(1)
    })

    it('closes dropdown after selecting an option', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      expect(screen.getByText('On True')).toBeVisible()

      const onTrueOption = screen.getByText('On True')
      await user.click(onTrueOption)

      // The dropdown should close - wait for the menu to be removed from the document
      await vi.waitFor(() => {
        expect(screen.queryByRole('menu')).not.toBeInTheDocument()
      })
    })
  })

  describe('branching nodes - approval', () => {
    it('renders dropdown with approved/rejected options for approval node', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.APPROVAL)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      expect(screen.getByText('On Approved')).toBeInTheDocument()
      expect(screen.getByText('On Rejected')).toBeInTheDocument()
    })

    it('calls onAddStep with "approved" handle when selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.APPROVAL)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const approvedOption = screen.getByText('On Approved')
      await user.click(approvedOption)

      expect(onAddStep).toHaveBeenCalledWith(EdgeHandleEnum.APPROVED)
    })

    it('calls onAddStep with "rejected" handle when selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.APPROVAL)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const rejectedOption = screen.getByText('On Rejected')
      await user.click(rejectedOption)

      expect(onAddStep).toHaveBeenCalledWith(EdgeHandleEnum.REJECTED)
    })
  })

  describe('branching nodes - loop', () => {
    it('renders dropdown with loop/done options for loop node', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.LOOP)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      expect(screen.getByText('In loop')).toBeInTheDocument()
      expect(screen.getByText('On done')).toBeInTheDocument()
    })

    it('calls onAddStep with "loop" handle when "In loop" is selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.LOOP)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const loopOption = screen.getByText('In loop')
      await user.click(loopOption)

      expect(onAddStep).toHaveBeenCalledWith(EdgeHandleEnum.LOOP)
    })

    it('calls onAddStep with "done" handle when "On done" is selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.LOOP)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const doneOption = screen.getByText('On done')
      await user.click(doneOption)

      expect(onAddStep).toHaveBeenCalledWith(EdgeHandleEnum.DONE)
    })
  })

  describe('branching nodes - switch', () => {
    it('renders dropdown with case paths and fallback for switch node', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      const switchNode = createMockNode(FlowNodeType.SWITCH, {
        type: 'switch',
        parameters: {
          cases: [
            { label: 'Path A', port: 'case_0' },
            { label: 'Path B', port: 'case_1' },
          ],
        },
      })

      render(<RightSidePill node={switchNode} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      expect(screen.getByText('On Path A')).toBeInTheDocument()
      expect(screen.getByText('On Path B')).toBeInTheDocument()
      expect(screen.getByText('Fallback')).toBeInTheDocument()
    })

    it('generates default labels for unlabeled switch cases', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      const switchNode = createMockNode(FlowNodeType.SWITCH, {
        type: 'switch',
        parameters: {
          cases: [{ port: 'case_0' }, { port: 'case_1' }, { port: 'case_2' }],
        },
      })

      render(<RightSidePill node={switchNode} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      expect(screen.getByText('On Path 1')).toBeInTheDocument()
      expect(screen.getByText('On Path 2')).toBeInTheDocument()
      expect(screen.getByText('On Path 3')).toBeInTheDocument()
      expect(screen.getByText('Fallback')).toBeInTheDocument()
    })

    it('calls onAddStep with case port when a case path is selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      const switchNode = createMockNode(FlowNodeType.SWITCH, {
        type: 'switch',
        parameters: {
          cases: [
            { label: 'Success', port: 'case_success' },
            { label: 'Error', port: 'case_error' },
          ],
        },
      })

      render(<RightSidePill node={switchNode} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const successOption = screen.getByText('On Success')
      await user.click(successOption)

      expect(onAddStep).toHaveBeenCalledWith('case_success')
      expect(onAddStep).toHaveBeenCalledTimes(1)
    })

    it('calls onAddStep with default handle when fallback is selected', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      const switchNode = createMockNode(FlowNodeType.SWITCH, {
        type: 'switch',
        parameters: {
          cases: [{ label: 'Case 1', port: 'case_0' }],
        },
      })

      render(<RightSidePill node={switchNode} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const fallbackOption = screen.getByText('Fallback')
      await user.click(fallbackOption)

      expect(onAddStep).toHaveBeenCalledWith(EdgeHandleEnum.DEFAULT)
      expect(onAddStep).toHaveBeenCalledTimes(1)
    })

    it('uses custom default_port when configured', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      const switchNode = createMockNode(FlowNodeType.SWITCH, {
        type: 'switch',
        parameters: {
          cases: [{ label: 'Case 1', port: 'case_0' }],
          default_port: 'custom_default',
        },
      })

      render(<RightSidePill node={switchNode} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      const fallbackOption = screen.getByText('Fallback')
      await user.click(fallbackOption)

      expect(onAddStep).toHaveBeenCalledWith('custom_default')
    })

    it('handles empty cases array gracefully', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      const switchNode = createMockNode(FlowNodeType.SWITCH, {
        type: 'switch',
        parameters: {
          cases: [],
        },
      })

      render(<RightSidePill node={switchNode} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.click(toggle)

      // Should only show fallback option
      expect(screen.getByText('Fallback')).toBeInTheDocument()
      expect(screen.queryByText(/^On Path/)).not.toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has no accessibility violations for non-branching node', async () => {
      const onAddStep = vi.fn()

      const { container } = render(<RightSidePill node={createMockNode(FlowNodeType.TASK)} onAddStep={onAddStep} />)

      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no accessibility violations for branching node', async () => {
      const onAddStep = vi.fn()

      const { container } = render(
        <RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />
      )

      expect(await axe(container)).toHaveNoViolations()
    })

    it('has no accessibility violations for branching node when dropdown is open', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      const { container } = render(
        <RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />
      )

      await user.click(screen.getByRole('button', { name: 'Add step…' }))

      expect(await axe(container)).toHaveNoViolations()
    })

    it('has accessible label on non-branching button', () => {
      const onAddStep = vi.fn()

      render(<RightSidePill node={createMockNode(FlowNodeType.TASK)} onAddStep={onAddStep} />)

      const button = screen.getByRole('button', { name: 'Add step' })
      expect(button).toHaveAccessibleName('Add step')
    })

    it('has accessible label on branching dropdown toggle', () => {
      const onAddStep = vi.fn()

      render(<RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      expect(toggle).toHaveAccessibleName('Add step…')
    })

    it('shows tooltip on non-branching button', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.TASK)} onAddStep={onAddStep} />)

      const button = screen.getByRole('button', { name: 'Add step' })
      await user.hover(button)

      expect(await screen.findByText('Add step')).toBeInTheDocument()
    })

    it('shows tooltip on branching dropdown toggle', async () => {
      const onAddStep = vi.fn()
      const user = userEvent.setup()

      render(<RightSidePill node={createMockNode(FlowNodeType.CONDITION)} onAddStep={onAddStep} />)

      const toggle = screen.getByRole('button', { name: 'Add step…' })
      await user.hover(toggle)

      expect(await screen.findByText('Add step…')).toBeInTheDocument()
    })
  })
})
