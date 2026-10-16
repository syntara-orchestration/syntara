import type { ApprovalActivity as ApprovalNodeType } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ApprovalStepComponent } from './ApprovalNode'

// Mock @xyflow/react
vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  useEdges: () => [],
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

describe('ApprovalStepComponent', () => {
  const baseApprovalNode = {
    type: 'approval',
    id: 'approval-1',
    name: 'Approve Deployment',
    parameters: {
      approver_timeout: 86400,
    },
  } as ApprovalNodeType

  const createNodeProps = (data: ApprovalNodeType) => ({
    id: data.id,
    data,
    type: 'approval' as const,
    position: { x: 0, y: 0 },
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    selected: false,
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    selectable: true,
    deletable: true,
    draggable: true,
  })

  describe('Rendering', () => {
    it('renders approval node with all key elements', () => {
      render(<ApprovalStepComponent {...createNodeProps(baseApprovalNode)} />)

      expect(screen.getByText('Approval')).toBeInTheDocument()
      expect(screen.getByText('Timeout')).toBeInTheDocument()
      expect(screen.getByText('86400s')).toBeInTheDocument()
      expect(screen.getByText('Approved')).toBeInTheDocument()
      expect(screen.getByText('Rejected')).toBeInTheDocument()
    })
  })

  describe('Approval Data', () => {
    it('does not render timeout section when config has no timeout', () => {
      const noTimeoutNode = {
        type: 'approval',
        id: 'approval-2',
        name: 'No Timeout Approval',
        parameters: {},
      } as ApprovalNodeType

      render(<ApprovalStepComponent {...createNodeProps(noTimeoutNode)} />)

      expect(screen.queryByText('Timeout')).not.toBeInTheDocument()
    })
  })

  describe('Branch Handles', () => {
    it('renders handles in correct order (approved first, then rejected)', () => {
      render(<ApprovalStepComponent {...createNodeProps(baseApprovalNode)} />)

      const handles = screen.getAllByText(/Approved|Rejected/)
      expect(handles[0]).toHaveTextContent('Approved')
      expect(handles[1]).toHaveTextContent('Rejected')
    })
  })

  describe('Node Structure', () => {
    it('renders with correct structure', () => {
      render(<ApprovalStepComponent {...createNodeProps(baseApprovalNode)} />)

      expect(screen.getByText('Approval')).toBeInTheDocument()
    })

    it('does not render expand/collapse toggle', () => {
      render(<ApprovalStepComponent {...createNodeProps(baseApprovalNode)} />)

      expect(screen.queryByTestId('node-expand-toggle')).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /expand step details|collapse step details/i })
      ).not.toBeInTheDocument()
    })
  })
})
