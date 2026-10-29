import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { ColorSchemeProvider } from '../../../providers/theme/ColorSchemeProvider'

import { RunStepDialog } from './RunStepDialog'

// Mock the workflow API client
const { mockPost } = vi.hoisted(() => ({
  mockPost: vi.fn(),
}))
vi.mock('../../../client', () => ({
  workflowFetchClient: {
    POST: mockPost,
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

// Mock Monaco editor since it doesn't work well in test environment
vi.mock('@patternfly/react-code-editor', () => ({
  CodeEditor: ({
    code,
    onCodeChange,
    customControls,
    'aria-label': ariaLabel,
  }: {
    code: string
    onCodeChange: (code: string) => void
    customControls?: React.ReactNode
    'aria-label'?: string
  }) => (
    <div data-testid="code-editor" aria-label={ariaLabel}>
      <textarea
        data-testid="code-textarea"
        value={code}
        onChange={(e) => onCodeChange(e.target.value)}
        aria-label={ariaLabel}
      />
      {customControls}
    </div>
  ),
  CodeEditorControl: ({
    icon,
    onClick,
    'aria-label': ariaLabel,
  }: {
    icon: React.ReactNode
    onClick: () => void
    'aria-label'?: string
  }) => (
    <button data-testid="expand-button" onClick={onClick} aria-label={ariaLabel}>
      {icon}
    </button>
  ),
  Language: {
    json: 'json',
  },
}))

describe('RunStepDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    nodeId: 'activity_1',
    nodeName: 'Test Script',
    workflowId: 'wf_123',
    predecessors: [{ id: 'pred_1', name: 'Previous Step' }],
  }

  const wrapper = ({ children }: { children: React.ReactNode }) => <ColorSchemeProvider>{children}</ColorSchemeProvider>

  beforeEach(() => {
    vi.clearAllMocks()
    // Default successful API response
    mockPost.mockResolvedValue({
      data: { id: 'execution_123' },
      error: null,
    })
  })

  describe('Choice Dialog', () => {
    it('renders choice dialog with node name in title', () => {
      // Arrange
      render(<RunStepDialog {...defaultProps} />, { wrapper })

      // Assert
      expect(screen.getByRole('heading', { name: 'Run Test Script?' })).toBeInTheDocument()
      expect(
        screen.getByText(/You are about to run this step manually\. Run all previous steps up to this one/)
      ).toBeInTheDocument()
    })

    it('shows "Run all previous steps" button as enabled', () => {
      // Arrange
      render(<RunStepDialog {...defaultProps} />, { wrapper })

      // Assert
      const runAllButton = screen.getByRole('button', { name: 'Run all previous steps' })
      expect(runAllButton).toBeEnabled()
    })

    it('disables "Set mock data" button when no predecessors', () => {
      // Arrange
      render(<RunStepDialog {...defaultProps} predecessors={[]} />, { wrapper })

      // Assert
      expect(screen.getByRole('button', { name: 'Set mock data' })).toBeDisabled()
    })

    it('transitions to mock editor when "Set mock data" is clicked', async () => {
      // Arrange
      const user = userEvent.setup()
      render(<RunStepDialog {...defaultProps} />, { wrapper })

      // Act
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      // Assert
      expect(screen.getByRole('heading', { name: 'Set mock data for Test Script' })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /mock json output data/i })).toBeInTheDocument()
    })

    it('closes dialog when Cancel is clicked', async () => {
      // Arrange
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<RunStepDialog {...defaultProps} onClose={onClose} />, { wrapper })

      // Act
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Assert
      expect(onClose).toHaveBeenCalledOnce()
    })

    it('has no accessibility violations in choice state', async () => {
      // Arrange
      const { container } = render(<RunStepDialog {...defaultProps} />, { wrapper })

      // Act
      const results = await axe(container)

      // Assert
      expect(results).toHaveNoViolations()
    })
  })

  describe('Mock Editor State', () => {
    async function openMockEditor() {
      const user = userEvent.setup()
      const view = render(<RunStepDialog {...defaultProps} />, { wrapper })
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))
      return { user, ...view }
    }

    it('renders mock editor with JSON input area', async () => {
      // Arrange & Act
      await openMockEditor()

      // Assert
      expect(screen.getByRole('heading', { name: 'Set mock data for Test Script' })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /mock json output data/i })).toBeInTheDocument()
      expect(screen.getByText(/Provide mock output data for the previous step/)).toBeInTheDocument()
    })

    it('allows entering JSON in the textarea', async () => {
      // Arrange
      const { user } = await openMockEditor()
      const textarea = screen.getByRole('textbox', { name: /mock json output data/i })

      // Act
      await user.clear(textarea)
      await user.click(textarea)
      await user.paste('{"key": "value"}')

      // Assert
      expect(textarea).toHaveValue('{"key": "value"}')
    })

    it('validates JSON and shows error for invalid input', async () => {
      // Arrange
      const { user } = await openMockEditor()
      const textarea = screen.getByRole('textbox', { name: /mock json output data/i })

      // Act
      await user.clear(textarea)
      await user.click(textarea)
      await user.paste('{invalid json')
      await user.click(screen.getByRole('button', { name: 'Run' }))

      // Assert — Error message may vary by browser/runtime
      expect(screen.getByText(/Unexpected|expected/i)).toBeInTheDocument()
    })

    it('calls onClose when Run is clicked with valid JSON', async () => {
      // Arrange
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<RunStepDialog {...defaultProps} onClose={onClose} />, { wrapper })
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))
      const textarea = screen.getByRole('textbox', { name: /mock json output data/i })

      // Act
      await user.clear(textarea)
      await user.click(textarea)
      await user.paste('{"hostname": "server1"}')
      await user.click(screen.getByRole('button', { name: 'Run' }))

      // Assert — waits for SUCCESS_AUTO_CLOSE_DELAY_MS timer to fire
      await waitFor(() => expect(onClose).toHaveBeenCalled(), { timeout: 1500 })
    })

    it('calls onClose when Run is clicked with empty JSON', async () => {
      // Arrange
      const user = userEvent.setup()
      const onClose = vi.fn()
      render(<RunStepDialog {...defaultProps} onClose={onClose} />, { wrapper })
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      // Act
      await user.click(screen.getByRole('button', { name: 'Run' }))

      // Assert — waits for SUCCESS_AUTO_CLOSE_DELAY_MS timer to fire
      await waitFor(() => expect(onClose).toHaveBeenCalled(), { timeout: 1500 })
    })

    it('closes dialog when Cancel is clicked from mock editor', async () => {
      // Arrange
      const onClose = vi.fn()
      render(<RunStepDialog {...defaultProps} onClose={onClose} />, { wrapper })
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      // Act
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Assert
      expect(onClose).toHaveBeenCalledOnce()
    })

    it('has no accessibility violations in mock editor state', async () => {
      // Arrange
      const { container } = render(<RunStepDialog {...defaultProps} />, { wrapper })
      const user = userEvent.setup()

      // Act
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))
      const results = await axe(container)

      // Assert
      expect(results).toHaveNoViolations()
    })
  })

  describe('State Reset', () => {
    it('resets to choice dialog when closed via Cancel', async () => {
      // Arrange
      const user = userEvent.setup()
      const onClose = vi.fn()
      const { rerender } = render(<RunStepDialog {...defaultProps} onClose={onClose} />, { wrapper })

      // Act 1 — Transition to mock editor
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))
      expect(screen.getByRole('heading', { name: 'Set mock data for Test Script' })).toBeInTheDocument()

      // Act 2 — Close via Cancel button (triggers handleClose which resets state)
      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      // Assert — onClose called and state reset on next open
      expect(onClose).toHaveBeenCalled()
      rerender(
        <ColorSchemeProvider>
          <RunStepDialog {...defaultProps} onClose={onClose} isOpen />
        </ColorSchemeProvider>
      )
      expect(screen.getByRole('heading', { name: 'Run Test Script?' })).toBeInTheDocument()
    })

    it('clears mock JSON when closed', async () => {
      // Arrange
      const user = userEvent.setup()
      const onClose = vi.fn()
      const { rerender } = render(<RunStepDialog {...defaultProps} onClose={onClose} />, { wrapper })

      // Act 1 — Enter JSON
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))
      const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
      await user.click(textarea)
      await user.paste('{"test": "data"}')

      // Act 2 — Close and reopen
      await user.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(onClose).toHaveBeenCalled()
      rerender(
        <ColorSchemeProvider>
          <RunStepDialog {...defaultProps} onClose={onClose} isOpen />
        </ColorSchemeProvider>
      )
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      // Assert
      const newTextarea = screen.getByRole('textbox', { name: /mock json output data/i })
      expect(newTextarea).toHaveValue('')
    })
  })

  describe('Button Placement', () => {
    it('has primary action leftmost in choice dialog', () => {
      // Arrange
      render(<RunStepDialog {...defaultProps} />, { wrapper })

      // Act — filter to named action buttons within the dialog
      const dialog = screen.getByRole('dialog')
      const allButtons = within(dialog).getAllByRole('button')
      const actionNames = ['Run all previous steps', 'Set mock data', 'Cancel']
      const actionButtons = allButtons.filter((btn) => actionNames.some((name) => btn.textContent?.includes(name)))

      // Assert — Primary (Run all) | Secondary (Set mock) | Link (Cancel)
      expect(actionButtons[0]).toHaveTextContent('Run all previous steps')
      expect(actionButtons[1]).toHaveTextContent('Set mock data')
      expect(actionButtons[2]).toHaveTextContent('Cancel')
    })

    it('has primary action leftmost in mock editor', async () => {
      // Arrange
      const user = userEvent.setup()
      render(<RunStepDialog {...defaultProps} />, { wrapper })
      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      // Act — filter to named action buttons within the dialog
      const dialog = screen.getByRole('dialog')
      const allButtons = within(dialog).getAllByRole('button')
      const actionButtons = allButtons.filter((btn) =>
        ['Run', 'Cancel'].some((name) => btn.textContent?.includes(name))
      )

      // Assert — Primary (Run) | Link (Cancel)
      expect(actionButtons[0]).toHaveTextContent('Run')
      expect(actionButtons[1]).toHaveTextContent('Cancel')
    })
  })

  // Control-Flow Node Support Tests
  describe('Control-Flow Node Support', () => {
    describe('Condition Node Target', () => {
      const conditionNodeProps = {
        isOpen: true,
        onClose: vi.fn(),
        nodeId: 'condition_1',
        nodeName: 'Check Environment',
        workflowId: 'wf_123',
        predecessors: [{ id: 'setup_1', name: 'Setup Task' }],
      }

      it('renders choice dialog with condition node name in title', () => {
        // Arrange & Act
        render(<RunStepDialog {...conditionNodeProps} />, { wrapper })

        // Assert
        expect(screen.getByRole('heading', { name: 'Run Check Environment?' })).toBeInTheDocument()
        expect(screen.getByText(/You are about to run this step manually/)).toBeInTheDocument()
      })

      it('enables mock data button for condition node with predecessors', () => {
        // Arrange & Act
        render(<RunStepDialog {...conditionNodeProps} />, { wrapper })

        // Assert
        const mockDataButton = screen.getByRole('button', { name: 'Set mock data' })
        expect(mockDataButton).toBeEnabled()
      })

      it('shows appropriate description for condition node mock data', async () => {
        // Arrange
        const user = userEvent.setup()
        render(<RunStepDialog {...conditionNodeProps} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Assert
        expect(screen.getByRole('heading', { name: 'Set mock data for Check Environment' })).toBeInTheDocument()
        expect(screen.getByText(/Provide mock output data for the previous step/)).toBeInTheDocument()
        expect(screen.getByText(/Setup Task/)).toBeInTheDocument()
      })

      it('handles condition node with multiple predecessors', async () => {
        // Arrange
        const conditionWithMultiplePredecessors = {
          ...conditionNodeProps,
          predecessors: [
            { id: 'initial_setup', name: 'Initial Setup' },
            { id: 'env_check', name: 'Environment Validation' },
          ],
        }
        const user = userEvent.setup()
        render(<RunStepDialog {...conditionWithMultiplePredecessors} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Assert — description mentions predecessor count, not individual names
        expect(screen.getByText(/2 predecessor steps/)).toBeInTheDocument()
        expect(screen.getByText(/Check Environment will execute/)).toBeInTheDocument()
      })

      it('has no accessibility violations for condition node dialog', async () => {
        // Arrange
        const { container } = render(<RunStepDialog {...conditionNodeProps} />, { wrapper })

        // Act
        const results = await axe(container)

        // Assert
        expect(results).toHaveNoViolations()
      })
    })

    describe('Converge Node Target', () => {
      const convergeNodeProps = {
        isOpen: true,
        onClose: vi.fn(),
        nodeId: 'converge_1',
        nodeName: 'Join Results',
        workflowId: 'wf_123',
        predecessors: [
          { id: 'branch_a', name: 'Branch A' },
          { id: 'branch_b', name: 'Branch B' },
          { id: 'branch_c', name: 'Branch C' },
        ],
      }

      it('renders choice dialog with converge node name in title', () => {
        // Arrange & Act
        render(<RunStepDialog {...convergeNodeProps} />, { wrapper })

        // Assert
        expect(screen.getByRole('heading', { name: 'Run Join Results?' })).toBeInTheDocument()
        expect(screen.getByText(/You are about to run this step manually/)).toBeInTheDocument()
      })

      it('enables mock data for converge with multiple inputs', () => {
        // Arrange & Act
        render(<RunStepDialog {...convergeNodeProps} />, { wrapper })

        // Assert
        const mockDataButton = screen.getByRole('button', { name: 'Set mock data' })
        expect(mockDataButton).toBeEnabled()
      })

      it('handles multiple predecessors in mock data description', async () => {
        // Arrange
        const user = userEvent.setup()
        render(<RunStepDialog {...convergeNodeProps} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Assert — description mentions predecessor count, not individual names
        expect(screen.getByRole('heading', { name: 'Set mock data for Join Results' })).toBeInTheDocument()
        expect(screen.getByText(/3 predecessor steps/)).toBeInTheDocument()
        expect(screen.getByText(/Join Results will execute/)).toBeInTheDocument()
      })

      it('supports mock data for converge node with multiple predecessor paths', async () => {
        // Arrange
        const user = userEvent.setup()
        render(<RunStepDialog {...convergeNodeProps} />, { wrapper })
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Act
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        const mockConvergeData = JSON.stringify(
          {
            branch_a_output: { status: 'complete', data: 'A result' },
            branch_b_output: { status: 'complete', data: 'B result' },
            branch_c_output: { status: 'complete', data: 'C result' },
          },
          null,
          2
        )

        await user.clear(textarea)
        await user.click(textarea)
        await user.paste(mockConvergeData)

        // Assert
        expect(textarea).toHaveValue(mockConvergeData)
        const runButton = screen.getByRole('button', { name: 'Run' })
        expect(runButton).toBeEnabled()
      })

      it('handles converge node with no predecessors gracefully', () => {
        // Arrange
        const convergeWithNoPredecessors = {
          ...convergeNodeProps,
          predecessors: [],
        }

        // Act & Assert
        render(<RunStepDialog {...convergeWithNoPredecessors} />, { wrapper })

        expect(screen.getByRole('heading', { name: 'Run Join Results?' })).toBeInTheDocument()
        const mockDataButton = screen.getByRole('button', { name: 'Set mock data' })
        expect(mockDataButton).toBeDisabled()
      })

      it('has no accessibility violations for converge node dialog', async () => {
        // Arrange
        const { container } = render(<RunStepDialog {...convergeNodeProps} />, { wrapper })

        // Act
        const results = await axe(container)

        // Assert
        expect(results).toHaveNoViolations()
      })
    })

    describe('Loop Node Target', () => {
      const loopNodeProps = {
        isOpen: true,
        onClose: vi.fn(),
        nodeId: 'loop_1',
        nodeName: 'Process Items',
        workflowId: 'wf_123',
        predecessors: [
          { id: 'get_items', name: 'Get Items' },
          { id: 'loop_body', name: 'Process Single Item' },
        ],
      }

      it('renders dialog for loop node with correct title', () => {
        // Arrange & Act
        render(<RunStepDialog {...loopNodeProps} />, { wrapper })

        // Assert
        expect(screen.getByRole('heading', { name: 'Run Process Items?' })).toBeInTheDocument()
        expect(screen.getByText(/You are about to run this step manually/)).toBeInTheDocument()
      })

      it('enables mock data for loop node with predecessors', () => {
        // Arrange & Act
        render(<RunStepDialog {...loopNodeProps} />, { wrapper })

        // Assert
        const mockDataButton = screen.getByRole('button', { name: 'Set mock data' })
        expect(mockDataButton).toBeEnabled()
      })

      it('handles loop body predecessors in mock data', async () => {
        // Arrange
        const user = userEvent.setup()
        render(<RunStepDialog {...loopNodeProps} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Assert — description mentions predecessor count, not individual names
        expect(screen.getByRole('heading', { name: 'Set mock data for Process Items' })).toBeInTheDocument()
        expect(screen.getByText(/2 predecessor steps/)).toBeInTheDocument()
        expect(screen.getByText(/Process Items will execute/)).toBeInTheDocument()
      })

      it('supports loop state mock data structure', async () => {
        // Arrange
        const user = userEvent.setup()
        render(<RunStepDialog {...loopNodeProps} />, { wrapper })
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Act
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        const mockLoopState = JSON.stringify(
          {
            items: ['test_item_1', 'test_item_2'],
            iteration_count: 0,
            loop_variables: { current_item: null },
          },
          null,
          2
        )

        await user.clear(textarea)
        await user.click(textarea)
        await user.paste(mockLoopState)

        // Assert
        expect(textarea).toHaveValue(mockLoopState)
        const runButton = screen.getByRole('button', { name: 'Run' })
        expect(runButton).toBeEnabled()
      })

      it('handles loop node with only setup predecessors', () => {
        // Arrange
        const loopWithSetupOnly = {
          ...loopNodeProps,
          predecessors: [{ id: 'setup_items', name: 'Setup Items' }],
        }

        // Act & Assert
        render(<RunStepDialog {...loopWithSetupOnly} />, { wrapper })

        expect(screen.getByRole('heading', { name: 'Run Process Items?' })).toBeInTheDocument()
        const mockDataButton = screen.getByRole('button', { name: 'Set mock data' })
        expect(mockDataButton).toBeEnabled()
      })

      it('has no accessibility violations for loop node dialog', async () => {
        // Arrange
        const { container } = render(<RunStepDialog {...loopNodeProps} />, { wrapper })

        // Act
        const results = await axe(container)

        // Assert
        expect(results).toHaveNoViolations()
      })
    })

    describe('Complex Predecessor Discovery', () => {
      it('includes predecessors from both condition branches', async () => {
        // Arrange
        const complexNodeProps = {
          isOpen: true,
          onClose: vi.fn(),
          nodeId: 'target_after_condition',
          nodeName: 'Final Step',
          workflowId: 'wf_123',
          predecessors: [
            { id: 'initial_setup', name: 'Initial Setup' },
            { id: 'condition_check', name: 'Environment Check' },
            { id: 'dev_branch', name: 'Dev Path' },
            { id: 'prod_branch', name: 'Prod Path' },
            { id: 'converge_point', name: 'Merge Results' },
          ],
        }

        const user = userEvent.setup()
        render(<RunStepDialog {...complexNodeProps} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Assert — description mentions predecessor count, not individual names
        expect(screen.getByRole('heading', { name: 'Set mock data for Final Step' })).toBeInTheDocument()
        expect(screen.getByText(/5 predecessor steps/)).toBeInTheDocument()
        expect(screen.getByText(/Final Step will execute/)).toBeInTheDocument()
      })

      it('handles complex mock data structure for nested control flow', async () => {
        // Arrange
        const complexNodeProps = {
          isOpen: true,
          onClose: vi.fn(),
          nodeId: 'complex_target',
          nodeName: 'Complex Target',
          workflowId: 'wf_123',
          predecessors: [
            { id: 'start', name: 'Start' },
            { id: 'loop_node', name: 'Process Loop' },
            { id: 'condition_in_loop', name: 'Loop Condition' },
            { id: 'loop_branch_a', name: 'Loop Branch A' },
            { id: 'loop_branch_b', name: 'Loop Branch B' },
            { id: 'loop_converge', name: 'Loop Converge' },
          ],
        }

        const user = userEvent.setup()
        render(<RunStepDialog {...complexNodeProps} />, { wrapper })
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))

        // Act
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        const complexMockData = JSON.stringify(
          {
            start_output: { data: 'initial' },
            loop_iterations: [
              {
                condition_result: true,
                branch_a_output: { result: 'A1' },
                branch_b_output: null,
                converge_output: { combined: 'A1' },
              },
              {
                condition_result: false,
                branch_a_output: null,
                branch_b_output: { result: 'B2' },
                converge_output: { combined: 'B2' },
              },
            ],
            final_loop_output: { total_iterations: 2 },
          },
          null,
          2
        )

        await user.clear(textarea)
        await user.click(textarea)
        await user.paste(complexMockData)

        // Assert
        expect(textarea).toHaveValue(complexMockData)
        const runButton = screen.getByRole('button', { name: 'Run' })
        expect(runButton).toBeEnabled()
      })

      it('handles empty predecessor list gracefully for complex scenarios', () => {
        // Arrange
        const emptyPredecessorsProps = {
          isOpen: true,
          onClose: vi.fn(),
          nodeId: 'isolated_node',
          nodeName: 'Isolated Node',
          workflowId: 'wf_123',
          predecessors: [],
        }

        // Act & Assert
        render(<RunStepDialog {...emptyPredecessorsProps} />, { wrapper })

        expect(screen.getByRole('heading', { name: 'Run Isolated Node?' })).toBeInTheDocument()
        const mockDataButton = screen.getByRole('button', { name: 'Set mock data' })
        expect(mockDataButton).toBeDisabled()
      })
    })

    describe('Control-Flow API Integration', () => {
      it('calls API correctly for condition node execution via run all', async () => {
        // Arrange
        const conditionNodeProps = {
          isOpen: true,
          onClose: vi.fn(),
          nodeId: 'condition_1',
          nodeName: 'Check Environment',
          workflowId: 'wf_123',
          predecessors: [{ id: 'setup_1', name: 'Setup Task' }],
        }

        const user = userEvent.setup()
        render(<RunStepDialog {...conditionNodeProps} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Run all previous steps' }))

        // Assert — uses /workflows/{workflow_id}/test with empty pre_resolved_nodes
        expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
          params: { path: { workflow_id: 'wf_123' } },
          body: {
            target_node_id: 'condition_1',
            pre_resolved_nodes: {},
            trigger_inputs: {},
            execute_target: true,
            trigger_node_id: '',
          },
        })
      })
    })

    // NEW TESTS: Control Flow Pre-Resolution for condition node control.next_port
    describe('Control Flow Pre-Resolution (Condition Node Control.next_port)', () => {
      describe('Control Flow Predecessor Detection', () => {
        it('includes control.next_port for condition node predecessors', async () => {
          // Arrange
          const conditionProps = {
            isOpen: true,
            onClose: vi.fn(),
            nodeId: 'target_node',
            nodeName: 'Target Task',
            workflowId: 'wf_123',
            predecessors: [
              {
                id: 'condition_1',
                name: 'Check Status',
                type: 'condition',
                portTowardTarget: 'true',
              },
            ],
          }

          const user = userEvent.setup()
          render(<RunStepDialog {...conditionProps} />, { wrapper })
          await user.click(screen.getByRole('button', { name: 'Set mock data' }))

          const mockData = { result: true }
          const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
          await user.clear(textarea)
          await user.paste(JSON.stringify(mockData))

          // Act
          await user.click(screen.getByRole('button', { name: 'Run' }))

          // Assert - THIS WILL FAIL until implementation is updated
          expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
            params: { path: { workflow_id: 'wf_123' } },
            body: {
              target_node_id: 'target_node',
              pre_resolved_nodes: {
                condition_1: {
                  output: { result: true },
                  control: { next_port: 'true' }, // ADDED for condition
                },
              },
              trigger_inputs: {},
              execute_target: true,
              trigger_node_id: '',
            },
          })
        })

        it('includes control.next_port for loop node predecessors with handle mapping', async () => {
          // Arrange
          const loopProps = {
            isOpen: true,
            onClose: vi.fn(),
            nodeId: 'target_node',
            nodeName: 'Target Task',
            workflowId: 'wf_123',
            predecessors: [
              {
                id: 'loop_1',
                name: 'Process Items',
                type: 'loop',
                portTowardTarget: 'loop', // React Flow handle
              },
            ],
          }

          const user = userEvent.setup()
          render(<RunStepDialog {...loopProps} />, { wrapper })
          await user.click(screen.getByRole('button', { name: 'Set mock data' }))

          const mockData = { items: ['a', 'b'] }
          const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
          await user.clear(textarea)
          await user.paste(JSON.stringify(mockData))

          // Act
          await user.click(screen.getByRole('button', { name: 'Run' }))

          // Assert - THIS WILL FAIL until implementation is updated
          expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
            params: { path: { workflow_id: 'wf_123' } },
            body: {
              target_node_id: 'target_node',
              pre_resolved_nodes: {
                loop_1: {
                  output: { items: ['a', 'b'] },
                  control: { next_port: 'iterate' }, // 'loop' handle → 'iterate' port
                },
              },
              trigger_inputs: {},
              execute_target: true,
              trigger_node_id: '',
            },
          })
        })

        it('includes control.next_port for approval node predecessors', async () => {
          // Arrange
          const approvalProps = {
            isOpen: true,
            onClose: vi.fn(),
            nodeId: 'target_node',
            nodeName: 'Target Task',
            workflowId: 'wf_123',
            predecessors: [
              {
                id: 'approval_1',
                name: 'Manual Approval',
                type: 'approval',
                portTowardTarget: 'approved',
              },
            ],
          }

          const user = userEvent.setup()
          render(<RunStepDialog {...approvalProps} />, { wrapper })
          await user.click(screen.getByRole('button', { name: 'Set mock data' }))

          const mockData = { approved: true }
          const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
          await user.clear(textarea)
          await user.paste(JSON.stringify(mockData))

          // Act
          await user.click(screen.getByRole('button', { name: 'Run' }))

          // Assert - THIS WILL FAIL until implementation is updated
          expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
            params: { path: { workflow_id: 'wf_123' } },
            body: {
              target_node_id: 'target_node',
              pre_resolved_nodes: {
                approval_1: {
                  output: { approved: true },
                  control: { next_port: 'approved' },
                },
              },
              trigger_inputs: {},
              execute_target: true,
              trigger_node_id: '',
            },
          })
        })
      })

      describe('Regular Task Predecessors (No Control)', () => {
        it('excludes control field for regular task predecessors', async () => {
          // Arrange
          const taskProps = {
            isOpen: true,
            onClose: vi.fn(),
            nodeId: 'target_node',
            nodeName: 'Target Task',
            workflowId: 'wf_123',
            predecessors: [
              {
                id: 'task_1',
                name: 'Setup Task',
                type: 'task',
                portTowardTarget: undefined, // No control flow
              },
            ],
          }

          const user = userEvent.setup()
          render(<RunStepDialog {...taskProps} />, { wrapper })
          await user.click(screen.getByRole('button', { name: 'Set mock data' }))

          const mockData = { hostname: 'server1' }
          const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
          await user.clear(textarea)
          await user.paste(JSON.stringify(mockData))

          // Act
          await user.click(screen.getByRole('button', { name: 'Run' }))

          // Assert - THIS WILL PASS (no control field expected)
          expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
            params: { path: { workflow_id: 'wf_123' } },
            body: {
              target_node_id: 'target_node',
              pre_resolved_nodes: {
                task_1: {
                  output: { hostname: 'server1' },
                  // NO control field for regular tasks
                },
              },
              trigger_inputs: {},
              execute_target: true,
              trigger_node_id: '',
            },
          })
        })
      })

      describe('Mixed Predecessor Types', () => {
        it('applies control fields only to control-flow predecessors', async () => {
          // Arrange
          const mixedProps = {
            isOpen: true,
            onClose: vi.fn(),
            nodeId: 'target_node',
            nodeName: 'Target Task',
            workflowId: 'wf_123',
            predecessors: [
              {
                id: 'condition_1',
                name: 'Check Status',
                type: 'condition',
                portTowardTarget: 'true',
              },
              {
                id: 'task_1',
                name: 'Setup Task',
                type: 'task',
                portTowardTarget: undefined,
              },
              {
                id: 'loop_1',
                name: 'Process Loop',
                type: 'loop',
                portTowardTarget: 'done',
              },
            ],
          }

          const user = userEvent.setup()
          render(<RunStepDialog {...mixedProps} />, { wrapper })
          await user.click(screen.getByRole('button', { name: 'Set mock data' }))

          const mockData = { result: true, items: ['a'], hostname: 'server1' }
          const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
          await user.clear(textarea)
          await user.paste(JSON.stringify(mockData))

          // Act
          await user.click(screen.getByRole('button', { name: 'Run' }))

          // Assert - THIS WILL FAIL until implementation is updated
          expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
            params: { path: { workflow_id: 'wf_123' } },
            body: {
              target_node_id: 'target_node',
              pre_resolved_nodes: {
                condition_1: {
                  output: { result: true, items: ['a'], hostname: 'server1' },
                  control: { next_port: 'true' }, // Control flow node
                },
                task_1: {
                  output: { result: true, items: ['a'], hostname: 'server1' },
                  // No control field for regular task
                },
                loop_1: {
                  output: { result: true, items: ['a'], hostname: 'server1' },
                  control: { next_port: 'complete' }, // 'done' → 'complete'
                },
              },
              trigger_inputs: {},
              execute_target: true,
              trigger_node_id: '',
            },
          })
        })
      })

      describe('Handle Mapping Edge Cases', () => {
        it('correctly maps React Flow handles to V2 API ports', async () => {
          // Arrange - Test all handle mappings
          const handleMappingProps = {
            isOpen: true,
            onClose: vi.fn(),
            nodeId: 'target_node',
            nodeName: 'Target Task',
            workflowId: 'wf_123',
            predecessors: [
              {
                id: 'loop_with_loop',
                name: 'Loop Continue',
                type: 'loop',
                portTowardTarget: 'loop', // → 'iterate'
              },
              {
                id: 'loop_with_done',
                name: 'Loop Exit',
                type: 'loop',
                portTowardTarget: 'done', // → 'complete'
              },
              {
                id: 'condition_true',
                name: 'Condition True',
                type: 'condition',
                portTowardTarget: 'true', // → 'true' (no mapping)
              },
              {
                id: 'approval_approved',
                name: 'Approval Approved',
                type: 'approval',
                portTowardTarget: 'approved', // → 'approved' (no mapping)
              },
            ],
          }

          const user = userEvent.setup()
          render(<RunStepDialog {...handleMappingProps} />, { wrapper })
          await user.click(screen.getByRole('button', { name: 'Set mock data' }))

          const mockData = { status: 'test' }
          const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
          await user.clear(textarea)
          await user.paste(JSON.stringify(mockData))

          // Act
          await user.click(screen.getByRole('button', { name: 'Run' }))

          // Assert - THIS WILL FAIL until implementation is updated
          expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
            params: { path: { workflow_id: 'wf_123' } },
            body: {
              target_node_id: 'target_node',
              pre_resolved_nodes: {
                loop_with_loop: {
                  output: { status: 'test' },
                  control: { next_port: 'iterate' }, // loop → iterate
                },
                loop_with_done: {
                  output: { status: 'test' },
                  control: { next_port: 'complete' }, // done → complete
                },
                condition_true: {
                  output: { status: 'test' },
                  control: { next_port: 'true' }, // true → true (no change)
                },
                approval_approved: {
                  output: { status: 'test' },
                  control: { next_port: 'approved' }, // approved → approved
                },
              },
              trigger_inputs: {},
              execute_target: true,
              trigger_node_id: '',
            },
          })
        })
      })

      describe('Error Cases and Fallbacks', () => {
        it('handles missing portTowardTarget for control flow nodes gracefully', async () => {
          // Arrange
          const missingPortProps = {
            isOpen: true,
            onClose: vi.fn(),
            nodeId: 'target_node',
            nodeName: 'Target Task',
            workflowId: 'wf_123',
            predecessors: [
              {
                id: 'condition_1',
                name: 'Condition',
                type: 'condition',
                portTowardTarget: undefined, // Missing port info
              },
            ],
          }

          const user = userEvent.setup()
          render(<RunStepDialog {...missingPortProps} />, { wrapper })
          await user.click(screen.getByRole('button', { name: 'Set mock data' }))

          const mockData = { result: true }
          const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
          await user.clear(textarea)
          await user.paste(JSON.stringify(mockData))

          // Act
          await user.click(screen.getByRole('button', { name: 'Run' }))

          // Assert - Should either exclude control field or show error
          expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
            params: { path: { workflow_id: 'wf_123' } },
            body: {
              target_node_id: 'target_node',
              pre_resolved_nodes: {
                condition_1: {
                  output: { result: true },
                  // No control field due to missing portTowardTarget
                },
              },
              trigger_inputs: {},
              execute_target: true,
              trigger_node_id: '',
            },
          })
        })
      })
    })
  })

  describe('Trigger Predecessor Support', () => {
    const triggerSchema = {
      type: 'object',
      properties: { host: { type: 'string' }, severity: { type: 'string' } },
    }

    const triggerPredecessorProps = {
      isOpen: true,
      onClose: vi.fn(),
      nodeId: 'step_1',
      nodeName: 'Run Script',
      workflowId: 'wf_123',
      predecessors: [{ id: 'trigger-0', name: 'Manual Trigger', isTrigger: true }],
      triggerInputSchema: triggerSchema,
    }

    it('enables "Set mock data" when trigger is the only predecessor', () => {
      render(<RunStepDialog {...triggerPredecessorProps} />, { wrapper })

      expect(screen.getByRole('button', { name: 'Set mock data' })).toBeEnabled()
    })

    it('pre-populates mock editor with trigger schema template', async () => {
      const user = userEvent.setup()
      render(<RunStepDialog {...triggerPredecessorProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      const textarea: HTMLTextAreaElement = screen.getByRole('textbox', { name: /mock json output data/i })
      expect(JSON.parse(textarea.value || '{}') as Record<string, unknown>).toEqual({ host: '', severity: '' })
    })

    it('pre-populates with raw data when schema has no type/properties', async () => {
      const rawData = { host: 'web-prod-04.example.com', severity: 'critical' }
      const user = userEvent.setup()
      render(<RunStepDialog {...triggerPredecessorProps} triggerInputSchema={rawData} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      const textarea: HTMLTextAreaElement = screen.getByRole('textbox', { name: /mock json output data/i })
      expect(JSON.parse(textarea.value || '{}') as Record<string, unknown>).toEqual(rawData)
    })

    it('sends trigger data as trigger_inputs, not pre_resolved_nodes', async () => {
      const user = userEvent.setup()
      render(<RunStepDialog {...triggerPredecessorProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Set mock data' }))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() =>
        expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
          params: { path: { workflow_id: 'wf_123' } },
          body: {
            target_node_id: 'step_1',
            pre_resolved_nodes: {},
            trigger_inputs: { host: '', severity: '' },
            execute_target: true,
            trigger_node_id: '',
          },
        })
      )
    })

    // AAP-89481: pinning mock data on the trigger's own Output panel must be
    // honored when running a downstream step via "Run step" -> "Use mock data",
    // not silently replaced with an empty schema template.
    it('pre-populates mock editor with pinned trigger mock data, not the empty schema template', async () => {
      const pinnedTriggerProps = {
        ...triggerPredecessorProps,
        pinnedMockData: { 'trigger-0': { host: 'web-01', severity: 'high' } },
      }
      const user = userEvent.setup()
      render(<RunStepDialog {...pinnedTriggerProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Use mock data' }))

      const textarea: HTMLTextAreaElement = screen.getByRole('textbox', { name: /mock json output data/i })
      expect(JSON.parse(textarea.value || '{}') as Record<string, unknown>).toEqual({
        host: 'web-01',
        severity: 'high',
      })
    })

    it('submits pinned trigger mock data as trigger_inputs, not the empty schema template', async () => {
      const pinnedTriggerProps = {
        ...triggerPredecessorProps,
        pinnedMockData: { 'trigger-0': { host: 'web-01', severity: 'high' } },
      }
      const user = userEvent.setup()
      render(<RunStepDialog {...pinnedTriggerProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Use mock data' }))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() =>
        expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
          params: { path: { workflow_id: 'wf_123' } },
          body: {
            target_node_id: 'step_1',
            pre_resolved_nodes: {},
            trigger_inputs: { host: 'web-01', severity: 'high' },
            execute_target: true,
            trigger_node_id: '',
          },
        })
      )
    })

    it('pre-populates keyed editor when trigger and regular predecessor coexist', async () => {
      const mixedProps = {
        ...triggerPredecessorProps,
        predecessors: [
          { id: 'trigger-0', name: 'Manual Trigger', isTrigger: true },
          { id: 'step_a', name: 'Step A' },
        ],
        pinnedMockData: { step_a: { result: 'ok' } },
      }
      const user = userEvent.setup()
      render(<RunStepDialog {...mixedProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Use mock data' }))

      const textarea: HTMLTextAreaElement = screen.getByRole('textbox', { name: /mock json output data/i })
      expect(JSON.parse(textarea.value || '{}') as Record<string, unknown>).toEqual({
        'trigger-0': { host: '', severity: '' },
        step_a: { result: 'ok' },
      })
    })

    it('submits keyed mixed mock data with trigger inputs and predecessor output', async () => {
      const mixedProps = {
        ...triggerPredecessorProps,
        predecessors: [
          { id: 'trigger-0', name: 'Manual Trigger', isTrigger: true },
          { id: 'step_a', name: 'Step A' },
        ],
        pinnedMockData: { step_a: { result: 'ok' } },
      }
      const user = userEvent.setup()
      render(<RunStepDialog {...mixedProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Use mock data' }))
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() =>
        expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
          params: { path: { workflow_id: 'wf_123' } },
          body: {
            target_node_id: 'step_1',
            pre_resolved_nodes: {
              step_a: { output: { result: 'ok' } },
            },
            trigger_inputs: { host: '', severity: '' },
            execute_target: true,
            trigger_node_id: '',
          },
        })
      )
    })

    it('submits keyed mixed mock data after user edits keyed JSON', async () => {
      const mixedProps = {
        ...triggerPredecessorProps,
        predecessors: [
          { id: 'trigger-0', name: 'Manual Trigger', isTrigger: true },
          { id: 'step_a', name: 'Step A' },
        ],
      }
      const user = userEvent.setup()
      render(<RunStepDialog {...mixedProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Set mock data' }))
      const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
      await user.clear(textarea)
      await user.click(textarea)
      await user.paste(
        JSON.stringify({
          'trigger-0': { host: 'prod-01', severity: 'high' },
          step_a: { result: 'edited' },
        })
      )
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() =>
        expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
          params: { path: { workflow_id: 'wf_123' } },
          body: {
            target_node_id: 'step_1',
            pre_resolved_nodes: {
              step_a: { output: { result: 'edited' } },
            },
            trigger_inputs: { host: 'prod-01', severity: 'high' },
            execute_target: true,
            trigger_node_id: '',
          },
        })
      )
    })

    it('does not pre-populate when trigger has no input schema', async () => {
      const noSchemaProps = {
        ...triggerPredecessorProps,
        triggerInputSchema: undefined,
      }
      const user = userEvent.setup()
      render(<RunStepDialog {...noSchemaProps} />, { wrapper })

      await user.click(screen.getByRole('button', { name: 'Set mock data' }))

      const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
      expect(textarea).toHaveValue('')
    })
  })

  describe('error handling and state guards', () => {
    describe('Error + Retry flow', () => {
      it('shows Retry button after API error and resets state on click', async () => {
        // Arrange
        const user = userEvent.setup()
        mockPost.mockResolvedValueOnce({
          data: null,
          error: { detail: 'Workflow not found' },
        })
        render(<RunStepDialog {...defaultProps} />, { wrapper })

        // Act 1 — trigger error
        await user.click(screen.getByRole('button', { name: 'Run all previous steps' }))

        // Assert — error state visible
        await waitFor(() => {
          expect(screen.getByText('Failed to start execution')).toBeInTheDocument()
          expect(screen.getByText('Workflow not found')).toBeInTheDocument()
        })
        expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()

        // Act 2 — click Retry
        mockPost.mockResolvedValueOnce({
          data: { id: 'execution_123' },
          error: null,
        })
        await user.click(screen.getByRole('button', { name: 'Retry' }))

        // Assert — state reset to idle, primary buttons visible again
        expect(screen.getByRole('button', { name: 'Run all previous steps' })).toBeInTheDocument()
        expect(screen.queryByText('Failed to start execution')).not.toBeInTheDocument()
      })
    })

    describe('Button disabled states during running', () => {
      it('disables both primary action buttons when runState is running', async () => {
        // Arrange
        const user = userEvent.setup()
        mockPost.mockImplementation(
          () =>
            new Promise((resolve) => {
              setTimeout(() => resolve({ data: { id: 'execution_123' }, error: null }), 1000)
            })
        )
        render(<RunStepDialog {...defaultProps} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Run all previous steps' }))

        // Assert — both buttons disabled during execution
        await waitFor(() => {
          const runButton = screen.getByRole('button', { name: /Running/ })
          expect(runButton).toBeDisabled()
          const mockDataButton = screen.getByRole('button', { name: 'Set mock data' })
          expect(mockDataButton).toBeDisabled()
        })
      })
    })

    describe('Cancel disabled during execution', () => {
      it('disables Cancel button when runState is running', async () => {
        // Arrange
        const user = userEvent.setup()
        mockPost.mockImplementation(
          () =>
            new Promise((resolve) => {
              setTimeout(() => resolve({ data: { id: 'execution_123' }, error: null }), 1000)
            })
        )
        render(<RunStepDialog {...defaultProps} />, { wrapper })

        // Act
        await user.click(screen.getByRole('button', { name: 'Run all previous steps' }))

        // Assert
        await waitFor(() => {
          const cancelButton = screen.getByRole('button', { name: 'Cancel' })
          expect(cancelButton).toBeDisabled()
        })
      })
    })

    describe('Success alert and auto-close flow', () => {
      it('shows success alert and disables Run button during success state (mock editor)', async () => {
        // Arrange
        const user = userEvent.setup()
        render(<RunStepDialog {...defaultProps} />, { wrapper })
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        await user.clear(textarea)
        await user.click(textarea)
        await user.paste('{"test": "data"}')

        // Act
        await user.click(screen.getByRole('button', { name: 'Run' }))

        // Assert — success alert appears and Run button is disabled
        await waitFor(() => {
          expect(screen.getByText('Execution started successfully')).toBeInTheDocument()
          const runButton = screen.getByRole('button', { name: 'Run' })
          expect(runButton).toBeDisabled()
        })
      })
    })

    describe('Error state in MockEditorView', () => {
      it('shows error alert and Retry button in mock editor view', async () => {
        // Arrange
        const user = userEvent.setup()
        mockPost.mockResolvedValueOnce({
          data: null,
          error: { detail: 'Mock data validation failed' },
        })
        render(<RunStepDialog {...defaultProps} />, { wrapper })

        // Act 1 — open mock editor
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        await user.clear(textarea)
        await user.click(textarea)
        await user.paste('{"test": "data"}')

        // Act 2 — trigger run
        await user.click(screen.getByRole('button', { name: 'Run' }))

        // Assert — error state visible in mock editor view
        await waitFor(() => {
          expect(screen.getByText('Failed to start execution')).toBeInTheDocument()
          expect(screen.getByText('Mock data validation failed')).toBeInTheDocument()
        })
        expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
      })
    })

    describe('getInitialMockJson multi-predecessor keying', () => {
      it('returns keyed object format when multiple predecessors exist', async () => {
        // Arrange
        const pinnedMockData = {
          pred_1: { output: 'first' },
          pred_2: { output: 'second' },
          pred_3: { output: 'third' },
        }
        const predecessors = [
          { id: 'pred_1', name: 'First' },
          { id: 'pred_2', name: 'Second' },
          { id: 'pred_3', name: 'Third' },
        ]
        const user = userEvent.setup()
        render(<RunStepDialog {...defaultProps} predecessors={predecessors} pinnedMockData={pinnedMockData} />, {
          wrapper,
        })

        // Act — click to open mock editor which initializes from pinnedMockData
        await user.click(screen.getByRole('button', { name: 'Use mock data' }))

        // Assert — verify keyed format in textarea
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        const expected = {
          pred_1: { output: 'first' },
          pred_2: { output: 'second' },
          pred_3: { output: 'third' },
        }
        expect(textarea).toHaveValue(JSON.stringify(expected, null, 2))
      })
    })

    describe('buildControlData for non-control-flow types', () => {
      it('omits control field for script node predecessors in API call', async () => {
        // Arrange
        const scriptProps = {
          ...defaultProps,
          predecessors: [
            {
              id: 'script_1',
              name: 'Script Task',
              type: 'script',
              portTowardTarget: 'output',
            },
          ],
        }
        const user = userEvent.setup()
        render(<RunStepDialog {...scriptProps} />, { wrapper })
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        await user.clear(textarea)
        await user.click(textarea)
        await user.paste('{"stdout": "test"}')

        // Act
        await user.click(screen.getByRole('button', { name: 'Run' }))

        // Assert — no control field in API call for script type
        await waitFor(
          () => {
            expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
              params: { path: { workflow_id: 'wf_123' } },
              body: {
                target_node_id: 'activity_1',
                pre_resolved_nodes: {
                  script_1: {
                    output: { stdout: 'test' },
                    // No control field
                  },
                },
                trigger_inputs: {},
                execute_target: true,
                trigger_node_id: '',
              },
            })
          },
          { timeout: 2000 }
        )
      })

      it('omits control field for HTTP node predecessors in API call', async () => {
        // Arrange
        const httpProps = {
          ...defaultProps,
          predecessors: [
            {
              id: 'http_1',
              name: 'HTTP Request',
              type: 'http',
              portTowardTarget: 'response',
            },
          ],
        }
        const user = userEvent.setup()
        render(<RunStepDialog {...httpProps} />, { wrapper })
        await user.click(screen.getByRole('button', { name: 'Set mock data' }))
        const textarea = screen.getByRole('textbox', { name: /mock json output data/i })
        await user.clear(textarea)
        await user.click(textarea)
        await user.paste('{"status": 200}')

        // Act
        await user.click(screen.getByRole('button', { name: 'Run' }))

        // Assert — no control field in API call for HTTP type
        await waitFor(
          () => {
            expect(mockPost).toHaveBeenCalledWith('/workflows/{workflow_id}/test', {
              params: { path: { workflow_id: 'wf_123' } },
              body: {
                target_node_id: 'activity_1',
                pre_resolved_nodes: {
                  http_1: {
                    output: { status: 200 },
                    // No control field
                  },
                },
                trigger_inputs: {},
                execute_target: true,
                trigger_node_id: '',
              },
            })
          },
          { timeout: 2000 }
        )
      })
    })
  })
})
