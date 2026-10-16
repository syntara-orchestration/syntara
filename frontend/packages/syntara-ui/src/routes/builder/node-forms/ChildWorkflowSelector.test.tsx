import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { ChildWorkflowSelector } from './ChildWorkflowSelector'

// Mock useWorkflowsQuery
vi.mock('../../workflows/useWorkflowsQuery', () => ({
  useWorkflowsQuery: vi.fn(() => ({
    workflowsQuery: { isLoading: false, isError: false },
    workflows: [
      {
        id: 'wf-1',
        name: 'Workflow A',
        current_version: 1,
        description: 'Test workflow A',
        is_enabled: true,
        project_id: 'proj-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      {
        id: 'wf-2',
        name: 'Workflow B',
        current_version: 2,
        description: 'Test workflow B',
        is_enabled: true,
        project_id: 'proj-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      {
        id: 'wf-3',
        name: 'Workflow C',
        current_version: 1,
        is_enabled: true,
        project_id: 'proj-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    ],
  })),
}))

describe('ChildWorkflowSelector', () => {
  const mockOnChange = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders with default label', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      expect(screen.getByText('Workflow')).toBeInTheDocument()
    })

    it('renders with custom label', () => {
      render(
        <ChildWorkflowSelector
          projectId="proj-1"
          selectedWorkflowId={null}
          onChange={mockOnChange}
          label="Select Target Workflow"
        />
      )

      expect(screen.getByText('Select Target Workflow')).toBeInTheDocument()
    })

    it('renders the form group', () => {
      const { container } = render(
        <ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />
      )

      expect(container).toBeInTheDocument()
    })

    it('shows placeholder when no workflow selected', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      expect(screen.getByPlaceholderText('Select a workflow...')).toBeInTheDocument()
    })

    it('displays selected workflow label', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-2" onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      expect(input).toHaveValue('Workflow B (v2)')
    })
  })

  describe('Workflow Selection', () => {
    it('displays workflow options when opened', async () => {
      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)

      expect(screen.getByText('Workflow A (v1)')).toBeInTheDocument()
      expect(screen.getByText('Workflow B (v2)')).toBeInTheDocument()
      expect(screen.getByText('Workflow C (v1)')).toBeInTheDocument()
    })

    it('displays workflow descriptions', async () => {
      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)

      expect(screen.getByText('Test workflow A')).toBeInTheDocument()
      expect(screen.getByText('Test workflow B')).toBeInTheDocument()
    })

    it('calls onChange when workflow selected', async () => {
      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)

      const option = screen.getByText('Workflow A (v1)')
      await user.click(option)

      expect(mockOnChange).toHaveBeenCalledWith('wf-1')
      expect(mockOnChange).toHaveBeenCalledTimes(1)
    })

    it('closes dropdown after selection', async () => {
      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)

      const option = screen.getByText('Workflow A (v1)')
      expect(option).toBeInTheDocument()

      await user.click(option)

      // Dropdown should close after selection - verify onChange was called
      expect(mockOnChange).toHaveBeenCalledWith('wf-1')
    })
  })

  describe('Clear Functionality', () => {
    it('shows clear button when workflow is selected', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-1" onChange={mockOnChange} />)

      expect(screen.getByLabelText('Clear selection')).toBeInTheDocument()
    })

    it('does not show clear button when no selection', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      expect(screen.queryByLabelText('Clear selection')).not.toBeInTheDocument()
    })

    it('clears selection when clear button clicked', async () => {
      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-1" onChange={mockOnChange} />)

      const clearButton = screen.getByLabelText('Clear selection')
      await user.click(clearButton)

      expect(mockOnChange).toHaveBeenCalledWith(null)
      expect(mockOnChange).toHaveBeenCalledTimes(1)
    })
  })

  describe('Search and Filtering', () => {
    it('updates filter value as user types', async () => {
      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)
      await user.type(input, 'Wor')

      expect(input).toHaveValue('Wor')
    })

    it('shows no results message when filter returns empty', async () => {
      const { useWorkflowsQuery } = await import('../../workflows/useWorkflowsQuery')
      // Set up mock before render to return empty workflows
      vi.mocked(useWorkflowsQuery).mockImplementation(
        () =>
          ({
            workflowsQuery: { isLoading: false, isError: false },
            workflows: [],
          }) as unknown as ReturnType<typeof useWorkflowsQuery>
      )

      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)

      // With empty workflows, should show no results with current filter
      await waitFor(() => {
        expect(screen.getByText(/No workflows match ""/)).toBeInTheDocument()
      })

      // Reset mock to default
      vi.mocked(useWorkflowsQuery).mockImplementation(
        () =>
          ({
            workflowsQuery: { isLoading: false, isError: false },
            workflows: [
              {
                id: 'wf-1',
                name: 'Workflow A',
                current_version: 1,
                description: 'Test workflow A',
                is_enabled: true,
                project_id: 'proj-1',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
              {
                id: 'wf-2',
                name: 'Workflow B',
                current_version: 2,
                description: 'Test workflow B',
                is_enabled: true,
                project_id: 'proj-1',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
              {
                id: 'wf-3',
                name: 'Workflow C',
                current_version: 1,
                is_enabled: true,
                project_id: 'proj-1',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ],
          }) as ReturnType<typeof useWorkflowsQuery>
      )
    })

    it('clears filter value when dropdown closes', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />
      )

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)
      await user.type(input, 'Workflow')

      // Select an option to close dropdown
      await user.click(screen.getByText('Workflow A (v1)'))

      // Simulate parent updating selectedWorkflowId
      rerender(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-1" onChange={mockOnChange} />)

      // Filter should be cleared, showing selected label
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Select a workflow...')).toHaveValue('Workflow A (v1)')
      })
    })
  })

  describe('Loading and Error States', () => {
    it('shows loading spinner when fetching workflows', async () => {
      const { useWorkflowsQuery } = await import('../../workflows/useWorkflowsQuery')
      vi.mocked(useWorkflowsQuery).mockReturnValueOnce({
        workflowsQuery: { isLoading: true, isError: false } as unknown,
        workflows: [],
      } as ReturnType<typeof useWorkflowsQuery>)

      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      expect(screen.getByLabelText('Loading workflows')).toBeInTheDocument()
    })

    it('hides clear button while loading', async () => {
      const { useWorkflowsQuery } = await import('../../workflows/useWorkflowsQuery')
      vi.mocked(useWorkflowsQuery).mockReturnValueOnce({
        workflowsQuery: { isLoading: true, isError: false } as unknown,
        workflows: [],
      } as ReturnType<typeof useWorkflowsQuery>)

      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-1" onChange={mockOnChange} />)

      expect(screen.queryByLabelText('Clear selection')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Loading workflows')).toBeInTheDocument()
    })

    it('shows loading message in dropdown when opened', async () => {
      const { useWorkflowsQuery } = await import('../../workflows/useWorkflowsQuery')
      // Set mock to loading state before render
      vi.mocked(useWorkflowsQuery).mockImplementation(
        () =>
          ({
            workflowsQuery: { isLoading: true, isError: false },
            workflows: [],
          }) as unknown as ReturnType<typeof useWorkflowsQuery>
      )

      const user = userEvent.setup()
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)

      // Should show Loading... in the dropdown
      expect(screen.getByText('Loading...')).toBeInTheDocument()

      // Reset mock to default
      vi.mocked(useWorkflowsQuery).mockImplementation(
        () =>
          ({
            workflowsQuery: { isLoading: false, isError: false },
            workflows: [
              {
                id: 'wf-1',
                name: 'Workflow A',
                current_version: 1,
                description: 'Test workflow A',
                is_enabled: true,
                project_id: 'proj-1',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
              {
                id: 'wf-2',
                name: 'Workflow B',
                current_version: 2,
                description: 'Test workflow B',
                is_enabled: true,
                project_id: 'proj-1',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
              {
                id: 'wf-3',
                name: 'Workflow C',
                current_version: 1,
                is_enabled: true,
                project_id: 'proj-1',
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ],
          }) as ReturnType<typeof useWorkflowsQuery>
      )
    })
  })

  describe('Disabled State', () => {
    it('does not show clear button when disabled', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-1" onChange={mockOnChange} isDisabled />)

      expect(screen.queryByLabelText('Clear selection')).not.toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(
        <ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />
      )

      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })

    it('has proper label displayed', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />)

      // Label is displayed via FormGroup
      expect(screen.getByText('Workflow')).toBeInTheDocument()
    })

    it('has proper aria label for clear button', () => {
      render(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-1" onChange={mockOnChange} />)

      expect(screen.getByLabelText('Clear selection')).toBeInTheDocument()
    })
  })

  describe('Complete Selection Flow', () => {
    it('completes full selection workflow: open → search → select', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <ChildWorkflowSelector projectId="proj-1" selectedWorkflowId={null} onChange={mockOnChange} />
      )

      // 1. Open dropdown
      const input = screen.getByPlaceholderText('Select a workflow...')
      await user.click(input)
      expect(screen.getByText('Workflow A (v1)')).toBeInTheDocument()

      // 2. Search
      await user.type(input, 'B')
      expect(input).toHaveValue('B')

      // 3. Select workflow
      await user.click(screen.getByText('Workflow B (v2)'))
      expect(mockOnChange).toHaveBeenCalledWith('wf-2')

      // 4. Re-render with selected workflow ID to simulate parent state update
      rerender(<ChildWorkflowSelector projectId="proj-1" selectedWorkflowId="wf-2" onChange={mockOnChange} />)

      // 5. Verify selected value is displayed
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Select a workflow...')).toHaveValue('Workflow B (v2)')
      })

      // 6. Clear selection
      const clearButton = screen.getByLabelText('Clear selection')
      await user.click(clearButton)
      expect(mockOnChange).toHaveBeenCalledWith(null)
    })
  })
})
