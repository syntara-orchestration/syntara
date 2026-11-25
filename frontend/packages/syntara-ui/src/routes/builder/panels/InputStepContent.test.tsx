import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { UpstreamStepInfo } from './hooks/useUpstreamSteps'
import { InputStepContent, InputPanelStepSection } from './InputStepContent'
import { getTriggerInputSchemaFields } from './utils/triggerSchemaUtils'

// Mock the getNodeOutputSchema function
vi.mock('@syntara/contracts', () => ({
  getNodeOutputSchema: vi.fn((type: string) => {
    if (type === 'script') {
      return {
        stdout: { type: 'string' },
        return_code: { type: 'number' },
      }
    }
    return null
  }),
  TriggerTypeEnum: {
    MANUAL_TRIGGER: 'manual_trigger',
    SCHEDULED: 'scheduled',
    EVENT: 'event',
    WEBHOOK_TRIGGER: 'webhook_trigger',
    EDA_TRIGGER: 'eda_trigger',
  },
}))

// Mock the view components
vi.mock('./InputEmptyState', () => ({
  InputEmptyState: ({ variant }: { variant: string }) => (
    <div data-testid="input-empty-state">{variant === 'connected-not-run' ? 'Input not available' : 'Other state'}</div>
  ),
}))

vi.mock('./views/InputSchemaPreview', () => ({
  InputSchemaPreview: ({ fields, nodeId }: { fields: Record<string, unknown>; nodeId: string }) => (
    <div data-testid="input-schema-preview">
      Schema preview for {nodeId} with {Object.keys(fields).length} fields
    </div>
  ),
}))

vi.mock('./views/InputSchemaView', () => ({
  InputSchemaView: ({ nodeId, searchTerm }: { nodeId: string; searchTerm: string }) => (
    <div data-testid="input-schema-view">
      Schema view for {nodeId} (search: {searchTerm || 'none'})
    </div>
  ),
}))

vi.mock('./views/InputTableView', () => ({
  InputTableView: ({ searchTerm }: { searchTerm: string }) => (
    <div data-testid="input-table-view">Table view (search: {searchTerm || 'none'})</div>
  ),
}))

vi.mock('./views/InputJsonView', () => ({
  InputJsonView: () => <div data-testid="input-json-view">JSON view</div>,
}))

vi.mock('./utils/triggerSchemaUtils', () => ({
  getTriggerInputSchemaFields: vi.fn(),
}))

const mockUpstreamNode: UpstreamStepInfo = {
  id: 'upstream-1',
  name: 'Previous Step',
  type: 'script',
}

const mockTriggerNode: UpstreamStepInfo = {
  id: 'trigger-0',
  name: 'Manual Trigger',
  type: 'manual_trigger',
}

const mockExecutionData = {
  'upstream-1': {
    stdout: 'output data',
    return_code: 0,
  },
}

describe('InputStepContent', () => {
  describe('Empty states', () => {
    it('renders "Input not available" when nodeData is null and no schema exists', () => {
      const unknownNode = { id: 'unknown-1', name: 'Unknown Step', type: 'unknown_type' }

      render(
        <InputStepContent
          upstreamNode={unknownNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
        />
      )

      expect(screen.getByTestId('input-empty-state')).toBeInTheDocument()
      expect(screen.getByText('Input not available')).toBeInTheDocument()
    })

    it('renders schema preview when nodeData is null but effectiveSchema exists', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
        />
      )

      expect(screen.getByTestId('input-schema-preview')).toBeInTheDocument()
      expect(screen.getByText(/Schema preview for upstream-1/)).toBeInTheDocument()
    })

    it('shows "Run previous steps" alert when props provided and no data', () => {
      const mockOnRunPreviousSteps = vi.fn()

      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
          onRunPreviousSteps={mockOnRunPreviousSteps}
          workflowId="workflow-123"
        />
      )

      expect(screen.getByText('Expected input fields')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Run previous steps' })).toBeInTheDocument()
    })

    it('does not show "Run previous steps" alert when onRunPreviousSteps is missing', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
          workflowId="workflow-123"
        />
      )

      expect(screen.queryByText('Expected input fields')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Run previous steps' })).not.toBeInTheDocument()
    })

    it('does not show "Run previous steps" alert when workflowId is missing', () => {
      const mockOnRunPreviousSteps = vi.fn()

      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
          onRunPreviousSteps={mockOnRunPreviousSteps}
        />
      )

      expect(screen.queryByText('Expected input fields')).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Run previous steps' })).not.toBeInTheDocument()
    })

    it('calls onRunPreviousSteps when button clicked', async () => {
      const user = userEvent.setup()
      const mockOnRunPreviousSteps = vi.fn()

      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
          onRunPreviousSteps={mockOnRunPreviousSteps}
          workflowId="workflow-123"
        />
      )

      await user.click(screen.getByRole('button', { name: 'Run previous steps' }))

      expect(mockOnRunPreviousSteps).toHaveBeenCalledTimes(1)
    })
  })

  describe('View switching', () => {
    it('renders schema view by default when data exists', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={true}
          mergedExecutionData={mockExecutionData}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
        />
      )

      expect(screen.getByTestId('input-schema-view')).toBeInTheDocument()
      expect(screen.getByText(/Schema view for upstream-1/)).toBeInTheDocument()
    })

    it('switches to table view when activeView is table', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={true}
          mergedExecutionData={mockExecutionData}
          triggers={undefined}
          activeView="table"
          searchTerm=""
        />
      )

      expect(screen.getByTestId('input-table-view')).toBeInTheDocument()
      expect(screen.getByText(/Table view/)).toBeInTheDocument()
    })

    it('switches to JSON view when activeView is json', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={true}
          mergedExecutionData={mockExecutionData}
          triggers={undefined}
          activeView="json"
          searchTerm=""
        />
      )

      expect(screen.getByTestId('input-json-view')).toBeInTheDocument()
      expect(screen.getByText('JSON view')).toBeInTheDocument()
    })
  })

  describe('expressionNodeId computation', () => {
    it.each(['manual_trigger', 'scheduled', 'event', 'webhook_trigger', 'eda_trigger'])(
      'sets expressionNodeId to "trigger" for %s type',
      (type) => {
        render(
          <InputStepContent
            upstreamNode={{ ...mockTriggerNode, type }}
            hasData={true}
            mergedExecutionData={{ 'trigger-0': { timestamp: '2025-01-01T00:00:00Z' } }}
            triggers={undefined}
            activeView="schema"
            searchTerm=""
          />
        )

        expect(screen.getByText('Schema view for trigger (search: none)')).toBeInTheDocument()
      }
    )

    it('sets expressionNodeId to node.id for non-trigger types', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={true}
          mergedExecutionData={mockExecutionData}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
        />
      )

      expect(screen.getByText(/Schema view for upstream-1/)).toBeInTheDocument()
    })
  })

  describe('Search term handling', () => {
    it('passes search term to schema view', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={true}
          mergedExecutionData={mockExecutionData}
          triggers={undefined}
          activeView="schema"
          searchTerm="test-search"
        />
      )

      expect(screen.getByText(/search: test-search/)).toBeInTheDocument()
    })

    it('passes search term to table view', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={true}
          mergedExecutionData={mockExecutionData}
          triggers={undefined}
          activeView="table"
          searchTerm="test-search"
        />
      )

      expect(screen.getByText(/search: test-search/)).toBeInTheDocument()
    })

    it('handles empty search term', () => {
      render(
        <InputStepContent
          upstreamNode={mockUpstreamNode}
          hasData={true}
          mergedExecutionData={mockExecutionData}
          triggers={undefined}
          activeView="schema"
          searchTerm=""
        />
      )

      expect(screen.getByText(/search: none/)).toBeInTheDocument()
    })
  })

  describe('Trigger schema handling', () => {
    it('uses trigger input_schema fields when available', () => {
      vi.mocked(getTriggerInputSchemaFields).mockReturnValue([
        { name: 'hostname', type: 'string', description: 'Host name' },
        { name: 'port', type: 'number', description: 'Port number' },
      ])

      render(
        <InputStepContent
          upstreamNode={mockTriggerNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={[{ id: 'trigger-0' }]}
          activeView="schema"
          searchTerm=""
        />
      )

      expect(screen.getByTestId('input-schema-preview')).toBeInTheDocument()
      expect(screen.getByText(/with 2 fields/)).toBeInTheDocument()
    })

    it('falls back to empty state when trigger has no input_schema', () => {
      vi.mocked(getTriggerInputSchemaFields).mockReturnValue(null)

      render(
        <InputStepContent
          upstreamNode={mockTriggerNode}
          hasData={false}
          mergedExecutionData={null}
          triggers={[{ id: 'trigger-0' }]}
          activeView="schema"
          searchTerm=""
        />
      )

      expect(screen.getByTestId('input-empty-state')).toBeInTheDocument()
    })
  })

  it('has no accessibility violations when showing empty state', async () => {
    const unknownNode = { id: 'unknown-1', name: 'Unknown Step', type: 'unknown_type' }

    const { container } = render(
      <InputStepContent
        upstreamNode={unknownNode}
        hasData={false}
        mergedExecutionData={null}
        triggers={undefined}
        activeView="schema"
        searchTerm=""
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when showing schema preview', async () => {
    const { container } = render(
      <InputStepContent
        upstreamNode={mockUpstreamNode}
        hasData={false}
        mergedExecutionData={null}
        triggers={undefined}
        activeView="schema"
        searchTerm=""
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with data views', async () => {
    const { container } = render(
      <InputStepContent
        upstreamNode={mockUpstreamNode}
        hasData={true}
        mergedExecutionData={mockExecutionData}
        triggers={undefined}
        activeView="schema"
        searchTerm=""
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('InputPanelStepSection', () => {
  const mockHandleUnpinSingle = vi.fn()

  beforeEach(() => {
    mockHandleUnpinSingle.mockClear()
  })

  it('renders children content', () => {
    render(
      <InputPanelStepSection
        upstreamNode={mockUpstreamNode}
        hasPinnedMock={false}
        handleUnpinSingle={mockHandleUnpinSingle}
      >
        <div data-testid="child-content">Child content</div>
      </InputPanelStepSection>
    )

    expect(screen.getByTestId('child-content')).toBeInTheDocument()
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('shows mock data pinned badge when hasPinnedMock is true', () => {
    render(
      <InputPanelStepSection
        upstreamNode={mockUpstreamNode}
        hasPinnedMock={true}
        handleUnpinSingle={mockHandleUnpinSingle}
      >
        <div>Content</div>
      </InputPanelStepSection>
    )

    expect(screen.getByText('Mock data pinned')).toBeInTheDocument()
  })

  it('does not show mock badge when hasPinnedMock is false', () => {
    render(
      <InputPanelStepSection
        upstreamNode={mockUpstreamNode}
        hasPinnedMock={false}
        handleUnpinSingle={mockHandleUnpinSingle}
      >
        <div>Content</div>
      </InputPanelStepSection>
    )

    expect(screen.queryByText('Mock data pinned')).not.toBeInTheDocument()
  })

  it('shows unpin button when mock is pinned', () => {
    render(
      <InputPanelStepSection
        upstreamNode={mockUpstreamNode}
        hasPinnedMock={true}
        handleUnpinSingle={mockHandleUnpinSingle}
      >
        <div>Content</div>
      </InputPanelStepSection>
    )

    expect(screen.getByRole('button', { name: /unpin data/i })).toBeInTheDocument()
  })

  it('calls handleUnpinSingle with node ID when unpin button clicked', async () => {
    const user = userEvent.setup()

    render(
      <InputPanelStepSection
        upstreamNode={mockUpstreamNode}
        hasPinnedMock={true}
        handleUnpinSingle={mockHandleUnpinSingle}
      >
        <div>Content</div>
      </InputPanelStepSection>
    )

    await user.click(screen.getByRole('button', { name: /unpin data/i }))

    expect(mockHandleUnpinSingle).toHaveBeenCalledWith('upstream-1')
    expect(mockHandleUnpinSingle).toHaveBeenCalledTimes(1)
  })

  it('has no accessibility violations without pinned mock', async () => {
    const { container } = render(
      <InputPanelStepSection
        upstreamNode={mockUpstreamNode}
        hasPinnedMock={false}
        handleUnpinSingle={mockHandleUnpinSingle}
      >
        <div>Content</div>
      </InputPanelStepSection>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with pinned mock', async () => {
    const { container } = render(
      <InputPanelStepSection
        upstreamNode={mockUpstreamNode}
        hasPinnedMock={true}
        handleUnpinSingle={mockHandleUnpinSingle}
      >
        <div>Content</div>
      </InputPanelStepSection>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
