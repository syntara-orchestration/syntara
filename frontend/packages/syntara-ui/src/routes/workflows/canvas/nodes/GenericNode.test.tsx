import type { TaskActivity } from '@syntara/contracts'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../../constants'

import { GenericStepComponent } from './GenericNode'

// Mock @xyflow/react
vi.mock('@xyflow/react', () => ({
  useReactFlow: () => ({
    deleteElements: vi.fn(),
    updateNode: vi.fn(),
    getNode: vi.fn(),
  }),
  useStore: (selector: (s: { transform: [number, number, number] }) => unknown) => selector({ transform: [0, 0, 1] }),
  useUpdateNodeInternals: () => vi.fn(),
  Handle: () => null,
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}))

describe('GenericStepComponent', () => {
  const baseGenericNode = {
    type: 'script',
    id: 'generic-1',
    name: 'Placeholder',
    parameters: {
      language: 'python',
      code: '',
    },
  } as TaskActivity

  const createNodeProps = (data: TaskActivity) => ({
    id: data.id,
    data,
    type: FlowNodeType.GENERIC,
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
    it('renders default message "Select a step type"', () => {
      render(<GenericStepComponent {...createNodeProps(baseGenericNode)} />)

      expect(screen.getByText('Select a step type')).toBeInTheDocument()
    })

    it('renders "Click to configure" title by default', () => {
      render(<GenericStepComponent {...createNodeProps(baseGenericNode)} />)

      expect(screen.getByText('Click to configure')).toBeInTheDocument()
    })
  })

  describe('Custom Message', () => {
    it('renders custom message when provided in metadata', () => {
      const nodeWithCustomMessage = {
        ...baseGenericNode,
        metadata: {
          __customMessage: 'Configure this step',
        },
      } as TaskActivity

      render(<GenericStepComponent {...createNodeProps(nodeWithCustomMessage)} />)

      expect(screen.getByText('Configure this step')).toBeInTheDocument()
    })

    it('does not show title when custom message is present', () => {
      const nodeWithCustomMessage = {
        ...baseGenericNode,
        metadata: {
          __customMessage: 'Custom setup message',
        },
      } as TaskActivity

      render(<GenericStepComponent {...createNodeProps(nodeWithCustomMessage)} />)

      expect(screen.queryByText('Click to configure')).not.toBeInTheDocument()
    })

    it('renders long custom message without overflow', () => {
      const nodeWithLongMessage = {
        ...baseGenericNode,
        metadata: {
          __customMessage: 'Configure this step with a long expression ${name_via_ai.analysis.default}',
        },
      } as TaskActivity

      render(<GenericStepComponent {...createNodeProps(nodeWithLongMessage)} />)

      expect(
        screen.getByText('Configure this step with a long expression ${name_via_ai.analysis.default}')
      ).toBeInTheDocument()
    })
  })

  describe('Reverse Handles', () => {
    it('handles reverseHandles metadata for loop-back paths', () => {
      const nodeWithReverseHandles = {
        ...baseGenericNode,
        metadata: {
          __reverseHandles: true,
        },
      } as TaskActivity

      render(<GenericStepComponent {...createNodeProps(nodeWithReverseHandles)} />)

      // Should render without crashing
      expect(screen.getByText('Select a step type')).toBeInTheDocument()
    })
  })

  describe('Execution State', () => {
    it('handles execution state data', () => {
      const nodeWithExecution = {
        ...baseGenericNode,
        __executionState: {
          status: 'pending',
        },
      } as TaskActivity

      render(<GenericStepComponent {...createNodeProps(nodeWithExecution)} />)

      // Should render without crashing
      expect(screen.getByText('Select a step type')).toBeInTheDocument()
    })
  })

  describe('Node Structure', () => {
    it('renders with correct structure', () => {
      render(<GenericStepComponent {...createNodeProps(baseGenericNode)} />)

      expect(screen.getByTestId('generic-flow-node')).toBeInTheDocument()
      expect(screen.getByText('Select a step type')).toBeInTheDocument()
    })

    it('renders with dashed border styling', () => {
      render(<GenericStepComponent {...createNodeProps(baseGenericNode)} />)

      const nodeRoot = screen.getByTestId('generic-flow-node')
      expect(nodeRoot).toHaveStyle({ borderStyle: 'dashed' })
    })
  })

  describe('Selection State', () => {
    it('renders when selected', () => {
      const props = createNodeProps(baseGenericNode)
      props.selected = true

      render(<GenericStepComponent {...props} />)

      expect(screen.getByText('Select a step type')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty metadata object', () => {
      const nodeWithEmptyMetadata = {
        ...baseGenericNode,
        metadata: {},
      } as TaskActivity

      render(<GenericStepComponent {...createNodeProps(nodeWithEmptyMetadata)} />)

      expect(screen.getByText('Select a step type')).toBeInTheDocument()
      expect(screen.getByText('Click to configure')).toBeInTheDocument()
    })
  })
})
