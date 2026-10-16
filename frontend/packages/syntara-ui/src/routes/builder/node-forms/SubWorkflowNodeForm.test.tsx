import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'

import { SubWorkflowNodeForm } from './SubWorkflowNodeForm'

// Mock useWorkflowStore
vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn(),
}))

// Mock useWorkflowsQuery (used by ChildWorkflowSelector)
vi.mock('../../workflows/useWorkflowsQuery', () => ({
  useWorkflowsQuery: vi.fn(() => ({
    workflowsQuery: { isLoading: false, isError: false },
    workflows: [
      {
        id: 'wf-1',
        name: 'Test Workflow',
        current_version: 1,
        description: 'Test workflow',
        is_enabled: true,
        project_id: 'proj-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    ],
  })),
}))

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('SubWorkflowNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useWorkflowStore).mockImplementation((selector) => selector({ projectId: 'proj-1' } as never))
  })

  describe('Rendering', () => {
    it('renders step name field', () => {
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      expect(screen.getByLabelText('Step name')).toBeInTheDocument()
    })

    it('renders child workflow selector', () => {
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      expect(screen.getByText('Child Workflow')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Select a workflow...')).toBeInTheDocument()
    })

    it('renders input mapping fields', () => {
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      expect(screen.getByText('Input Mapping')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Add input mapping' })).toBeInTheDocument()
    })

    it('populates fields with initial data', () => {
      renderWithQueryClient(
        <SubWorkflowNodeForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            name: 'Existing Step',
            workflow_id: 'wf-1',
            input_mapping: [{ id: 'i1', key: 'host', value: '${ inventory_host }' }],
          }}
        />
      )

      expect(screen.getByLabelText('Step name')).toHaveValue('Existing Step')
      expect(screen.getByPlaceholderText('Select a workflow...')).toHaveValue('Test Workflow (v1)')
      expect(screen.getByDisplayValue('host')).toBeInTheDocument()
      expect(screen.getByDisplayValue('${ inventory_host }')).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('submits with step name only', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      await user.type(screen.getByLabelText('Step name'), 'My Sub-workflow')
      fireEvent.submit(screen.getByTestId('sub-workflow-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'My Sub-workflow',
            workflow_id: null,
            input_mapping: [],
          })
        )
      })
    })

    it('submits with workflow selected', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      await user.type(screen.getByLabelText('Step name'), 'Call Workflow')
      const workflowInput = screen.getByPlaceholderText('Select a workflow...')
      await user.click(workflowInput)
      await user.click(screen.getByText('Test Workflow (v1)'))
      fireEvent.submit(screen.getByTestId('sub-workflow-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Call Workflow',
            workflow_id: 'wf-1',
            input_mapping: [],
          })
        )
      })
    })

    it('submits with input mapping', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      await user.type(screen.getByLabelText('Step name'), 'With Inputs')
      await user.click(screen.getByRole('button', { name: 'Add input mapping' }))

      const keyInput = screen.getByLabelText('Child input name 1')
      const valueInput = screen.getByLabelText('Parent value 1')
      await user.type(keyInput, 'target_host')
      await user.type(valueInput, '${ inventory_host }')
      fireEvent.submit(screen.getByTestId('sub-workflow-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'With Inputs',
            workflow_id: null,
            input_mapping: [expect.objectContaining({ key: 'target_host', value: '${ inventory_host }' })],
          })
        )
      })
    })

    it('submits complete form with all fields', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      await user.type(screen.getByLabelText('Step name'), 'Complete Step')

      const workflowInput = screen.getByPlaceholderText('Select a workflow...')
      await user.click(workflowInput)
      await user.click(screen.getByText('Test Workflow (v1)'))

      await user.click(screen.getByRole('button', { name: 'Add input mapping' }))
      await user.type(screen.getByLabelText('Child input name 1'), 'host')
      await user.type(screen.getByLabelText('Parent value 1'), '${ my_host }')
      fireEvent.submit(screen.getByTestId('sub-workflow-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Complete Step',
            workflow_id: 'wf-1',
            input_mapping: [expect.objectContaining({ key: 'host', value: '${ my_host }' })],
          })
        )
      })
    })
  })

  describe('Validation', () => {
    it('does not submit when name is empty', async () => {
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      fireEvent.submit(screen.getByTestId('sub-workflow-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).not.toHaveBeenCalled()
      })
    })

    it('trims whitespace from step name', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      await user.type(screen.getByLabelText('Step name'), '   Trimmed   ')
      fireEvent.submit(screen.getByTestId('sub-workflow-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Trimmed',
          })
        )
      })
    })
  })

  describe('Input Mapping Management', () => {
    it('disables input mapping when no workflow selected', () => {
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      const addButton = screen.getByRole('button', { name: 'Add input mapping' })
      expect(addButton).toBeDisabled()
    })

    it('enables input mapping when workflow is selected', () => {
      renderWithQueryClient(
        <SubWorkflowNodeForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            name: 'Test',
            workflow_id: 'wf-1',
            input_mapping: [],
          }}
        />
      )

      const addButton = screen.getByRole('button', { name: 'Add input mapping' })
      expect(addButton).toBeEnabled()
    })

    it('adds multiple input mappings', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      await user.type(screen.getByLabelText('Step name'), 'Multi Input')
      await user.click(screen.getByRole('button', { name: 'Add input mapping' }))
      await user.click(screen.getByRole('button', { name: 'Add input mapping' }))

      const keyInputs = screen.getAllByLabelText(/Child input name/i)
      const valueInputs = screen.getAllByLabelText(/Parent value/i)

      await user.type(keyInputs[0], 'host')
      await user.type(valueInputs[0], '${ my_host }')
      await user.type(keyInputs[1], 'port')
      await user.type(valueInputs[1], '22')
      fireEvent.submit(screen.getByTestId('sub-workflow-node-form'))

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Multi Input',
            input_mapping: [
              expect.objectContaining({ key: 'host', value: '${ my_host }' }),
              expect.objectContaining({ key: 'port', value: '22' }),
            ],
          })
        )
      })
    })

    it('removes input mapping', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(
        <SubWorkflowNodeForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            name: 'Test',
            workflow_id: null,
            input_mapping: [
              { id: 'i1', key: 'host', value: '${ my_host }' },
              { id: 'i2', key: 'port', value: '22' },
            ],
          }}
        />
      )

      const removeButtons = screen.getAllByRole('button', { name: /Remove input mapping/i })
      await user.click(removeButtons[0])

      expect(screen.queryByDisplayValue('host')).not.toBeInTheDocument()
      expect(screen.getByDisplayValue('port')).toBeInTheDocument()
    })
  })

  describe('Child Workflow Selection', () => {
    it('selects and clears workflow', async () => {
      const user = userEvent.setup()
      renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      await user.type(screen.getByLabelText('Step name'), 'Test')

      const workflowInput = screen.getByPlaceholderText('Select a workflow...')
      await user.click(workflowInput)
      await user.click(screen.getByText('Test Workflow (v1)'))

      expect(workflowInput).toHaveValue('Test Workflow (v1)')

      const clearButton = screen.getByLabelText('Clear selection')
      await user.click(clearButton)

      expect(workflowInput).toHaveValue('')
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderWithQueryClient(<SubWorkflowNodeForm onSubmit={mockOnSubmit} onCancel={vi.fn()} />)

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations with data', async () => {
      const { container } = renderWithQueryClient(
        <SubWorkflowNodeForm
          onSubmit={mockOnSubmit}
          onCancel={vi.fn()}
          initialData={{
            name: 'Test Step',
            workflow_id: 'wf-1',
            input_mapping: [{ id: 'i1', key: 'host', value: '${ my_host }' }],
          }}
        />
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
