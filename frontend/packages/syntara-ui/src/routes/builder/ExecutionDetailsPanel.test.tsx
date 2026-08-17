import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { executionsClient } from '../../client'

import { ExecutionDetailsPanel, type WorkflowDefShape } from './ExecutionDetailsPanel'

/** v1 workflow definition: names live under workflow.activities */
const WORKFLOW_DEF: WorkflowDefShape = {
  workflow: {
    activities: [
      { id: 'task-1', name: 'Process data' },
      { id: 'task-2', name: 'Send notification' },
    ],
  },
}

/** v2 workflow definition: names live under top-level nodes[] */
const WORKFLOW_DEF_V2: WorkflowDefShape = {
  nodes: [
    { id: 'task-1', name: 'My AI Agent' },
    { id: 'task-2', name: 'Data Processor' },
  ],
}

/** Mixed definition: both nodes (v2) and workflow.activities (v1) present */
const WORKFLOW_DEF_MIXED: WorkflowDefShape = {
  nodes: [
    { id: 'task-1', name: 'V2 Agent Name' },
    { id: 'task-2', name: 'V2 Processor Name' },
  ],
  workflow: {
    activities: [
      { id: 'task-1', name: 'V1 Process data' },
      { id: 'task-2', name: 'V1 Send notification' },
    ],
  },
}

const EXECUTION = {
  data: {
    id: 'exec-123',
    workflow_id: 'wf-123',
    workflow_version_id: 'wfv-123',
    temporal_workflow_id: 'temporal-123',
    status: 'running',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    created_by: 'user-1',
    updated_by: null,
    completed_at: null,
    input_data: {},
    error_details: null,
    activities: [
      {
        activity_id: 'task-1',
        status: 'completed',
        started_at: '2024-01-01T00:00:00Z',
        completed_at: '2024-01-01T00:01:00Z',
      },
      { activity_id: 'task-2', status: 'running', started_at: '2024-01-01T00:01:00Z', completed_at: null },
    ],
  },
  isLoading: false,
  error: null,
}

vi.mock('../../client', () => ({
  executionsClient: { useQuery: vi.fn(() => EXECUTION) },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('./ExecutionStatus', () => ({
  StatusLabel: ({ status }: { status: string }) => <div data-testid="status-label">{status}</div>,
  ActivityStatusLabel: ({ status }: { status: string }) => <div data-testid="activity-status-label">{status}</div>,
}))

function renderPanel(workflowDefinition?: WorkflowDefShape | null) {
  return render(<ExecutionDetailsPanel executionId="exec-123" workflowDefinition={workflowDefinition} />)
}

function renderPanelWithClose(onClosePanel: () => void, headerLabel?: string) {
  return render(
    <ExecutionDetailsPanel
      executionId="exec-123"
      workflowDefinition={WORKFLOW_DEF}
      headerLabel={headerLabel}
      onClosePanel={onClosePanel}
    />
  )
}

describe('ExecutionDetailsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  describe('header', () => {
    it('renders title and execution status', () => {
      renderPanel(WORKFLOW_DEF)

      expect(screen.getByText('Current run details')).toBeInTheDocument()
      expect(screen.getByTestId('status-label')).toHaveTextContent('running')
    })

    it('shows a start/completed timestamp range when the execution has finished', () => {
      vi.mocked(executionsClient.useQuery).mockReturnValue({
        ...EXECUTION,
        data: { ...EXECUTION.data, status: 'completed', completed_at: '2024-01-01T00:05:00Z' },
      } as never)

      const { container } = renderPanel(WORKFLOW_DEF)

      expect(container.textContent).toContain(' - ')

      vi.mocked(executionsClient.useQuery).mockReturnValue(EXECUTION as never)
    })

    it('shows elapsed time that ticks while running', () => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2024-01-01T00:00:30Z'))

      renderPanel(WORKFLOW_DEF)
      expect(screen.getByText(/Elapsed time: 30s/)).toBeInTheDocument()

      act(() => {
        vi.advanceTimersByTime(2000)
      })
      expect(screen.getByText(/Elapsed time: 32s/)).toBeInTheDocument()

      vi.useRealTimers()
    })
  })

  describe('table rows', () => {
    it('renders activity names from workflow definition', () => {
      renderPanel(WORKFLOW_DEF)

      expect(screen.getByText('Process data')).toBeInTheDocument()
      expect(screen.getByText('Send notification')).toBeInTheDocument()
    })

    it('renders a status label per activity', () => {
      renderPanel(WORKFLOW_DEF)

      const labels = screen.getAllByTestId('activity-status-label')
      expect(labels).toHaveLength(2)
      expect(labels[0]).toHaveTextContent('completed')
      expect(labels[1]).toHaveTextContent('running')
    })
  })

  describe('activity table columns', () => {
    it('renders original column headers without sort controls', () => {
      renderPanel(WORKFLOW_DEF)

      expect(screen.getByRole('columnheader', { name: /Name/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Started/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Ended/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Elapsed time/i })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: /Status/i })).toBeInTheDocument()
      expect(screen.queryByRole('columnheader', { name: /Type/i })).not.toBeInTheDocument()
    })

    it('orders activities chronologically by default (earlier started first)', () => {
      renderPanel(WORKFLOW_DEF)

      const labels = screen.getAllByTestId('activity-status-label')
      // task-1 started at 00:00, task-2 at 00:01 — chronological keeps that order
      expect(labels[0]).toHaveTextContent('completed')
      expect(labels[1]).toHaveTextContent('running')
    })

    it('keeps chronological order in Details compact list', async () => {
      const user = userEvent.setup()
      renderPanel(WORKFLOW_DEF)

      await user.click(screen.getByRole('tab', { name: 'Details' }))

      const activityList = screen.getByRole('grid', { name: 'Activity list' })
      const rows = within(activityList).getAllByRole('row')
      expect(rows[0]).toHaveTextContent('Process data')
      expect(rows[1]).toHaveTextContent('Send notification')
    })
  })

  describe('v2 workflow definition (nodes[])', () => {
    it('shows activity names from v2 nodes array', () => {
      renderPanel(WORKFLOW_DEF_V2)

      expect(screen.getByText('My AI Agent')).toBeInTheDocument()
      expect(screen.getByText('Data Processor')).toBeInTheDocument()
    })

    it('does not fall back to activity IDs when v2 nodes provide names', () => {
      renderPanel(WORKFLOW_DEF_V2)

      expect(screen.queryByText('task-1')).not.toBeInTheDocument()
      expect(screen.queryByText('task-2')).not.toBeInTheDocument()
    })
  })

  describe('v2 nodes takes precedence over v1 workflow.activities', () => {
    it('uses v2 node names when both nodes and workflow.activities are present', () => {
      renderPanel(WORKFLOW_DEF_MIXED)

      expect(screen.getByText('V2 Agent Name')).toBeInTheDocument()
      expect(screen.getByText('V2 Processor Name')).toBeInTheDocument()

      expect(screen.queryByText('V1 Process data')).not.toBeInTheDocument()
      expect(screen.queryByText('V1 Send notification')).not.toBeInTheDocument()
    })
  })

  describe('fallback behavior', () => {
    it('uses activity ID when no workflow definition is provided', () => {
      renderPanel()

      expect(screen.getByText('task-1')).toBeInTheDocument()
      expect(screen.getByText('task-2')).toBeInTheDocument()
    })

    it('uses activity ID when workflow definition is null', () => {
      renderPanel(null)

      expect(screen.getByText('task-1')).toBeInTheDocument()
      expect(screen.getByText('task-2')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderPanel(WORKFLOW_DEF)

      // Exclude aria-valid-attr-value: PF6 Tabs renders aria-controls pointing to
      // tab panels that are not in the DOM (only the active panel is rendered).
      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })
  })

  describe('headerLabel and close button', () => {
    it('renders default title when headerLabel is not provided', () => {
      renderPanel(WORKFLOW_DEF)

      expect(screen.getByText('Current run details')).toBeInTheDocument()
    })

    it('renders custom headerLabel when provided', () => {
      renderPanelWithClose(vi.fn(), 'Most recent run details')

      expect(screen.getByText('Most recent run details')).toBeInTheDocument()
      expect(screen.queryByText('Current run details')).not.toBeInTheDocument()
    })

    it('does not render a close button when onClosePanel is not provided', () => {
      renderPanel(WORKFLOW_DEF)

      expect(screen.queryByRole('button', { name: 'Close run details panel' })).not.toBeInTheDocument()
    })

    it('renders a close button when onClosePanel is provided', () => {
      renderPanelWithClose(vi.fn())

      expect(screen.getByRole('button', { name: 'Close run details panel' })).toBeInTheDocument()
    })

    it('calls onClosePanel when the close button is clicked', async () => {
      const user = userEvent.setup()
      const onClosePanel = vi.fn()
      renderPanelWithClose(onClosePanel)

      await user.click(screen.getByRole('button', { name: 'Close run details panel' }))

      expect(onClosePanel).toHaveBeenCalledTimes(1)
    })
  })

  describe('view mode toggle', () => {
    it('renders Overview and Details tabs', () => {
      renderPanel(WORKFLOW_DEF)

      expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: 'Details' })).toBeInTheDocument()
    })

    it('defaults to Overview mode with activity table visible', () => {
      renderPanel(WORKFLOW_DEF)

      expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'false')
      expect(screen.getByText('Process data')).toBeInTheDocument()
    })

    it('switches to Details mode showing no-selection state', async () => {
      const user = userEvent.setup()
      renderPanel(WORKFLOW_DEF)

      await user.click(screen.getByRole('tab', { name: 'Details' }))

      expect(screen.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByText(/Select a step/)).toBeInTheDocument()
    })

    it('switches back to Overview mode', async () => {
      const user = userEvent.setup()
      renderPanel(WORKFLOW_DEF)

      await user.click(screen.getByRole('tab', { name: 'Details' }))
      await user.click(screen.getByRole('tab', { name: 'Overview' }))

      expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
      expect(screen.getByText('Process data')).toBeInTheDocument()
    })
  })

  describe('activity filters', () => {
    it('renders a filter toolbar in overview mode', () => {
      renderPanel(WORKFLOW_DEF)

      const region = screen.getByRole('region', { name: 'Activity filter' })
      expect(within(region).getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    })

    it('renders a filter toolbar in details mode', async () => {
      const user = userEvent.setup()
      renderPanel(WORKFLOW_DEF)

      await user.click(screen.getByRole('tab', { name: 'Details' }))

      const region = screen.getByRole('region', { name: 'Activity filter' })
      expect(within(region).getByRole('search', { name: 'Filters' })).toBeInTheDocument()
    })

    it('shows empty state when filters match no activities', async () => {
      const user = userEvent.setup()
      renderPanel(WORKFLOW_DEF)

      const toolbar = screen.getByRole('search', { name: 'Filters' })
      const filterInput = within(toolbar).getByRole('textbox')
      await user.type(filterInput, 'nonexistent-activity-xyz{Enter}')

      expect(screen.getByText('No results found')).toBeInTheDocument()
    })

    it('shows clear all button in empty state', async () => {
      const user = userEvent.setup()
      renderPanel(WORKFLOW_DEF)

      const toolbar = screen.getByRole('search', { name: 'Filters' })
      const filterInput = within(toolbar).getByRole('textbox')
      await user.type(filterInput, 'nonexistent-activity-xyz{Enter}')

      expect(screen.getByRole('button', { name: 'Clear all filters' })).toBeInTheDocument()
    })

    it('persists filters when switching between Overview and Details tabs', async () => {
      const user = userEvent.setup()
      renderPanel(WORKFLOW_DEF)

      const toolbar = screen.getByRole('search', { name: 'Filters' })
      const filterInput = within(toolbar).getByRole('textbox')
      await user.type(filterInput, 'Process{Enter}')

      expect(screen.getByText('Process data')).toBeInTheDocument()
      expect(screen.queryByText('Send notification')).not.toBeInTheDocument()

      await user.click(screen.getByRole('tab', { name: 'Details' }))

      expect(screen.getByText('Process data')).toBeInTheDocument()
      expect(screen.queryByText('Send notification')).not.toBeInTheDocument()
    })
  })

  describe('accessibility (view mode toggle)', () => {
    // PatternFly Tabs generates aria-controls with random IDs that don't match
    // rendered panel IDs in jsdom — a known upstream issue, not an application bug.
    const axeTabRules = { rules: { 'aria-valid-attr-value': { enabled: false } } }

    it('has no violations in default state', async () => {
      const { container } = renderPanel(WORKFLOW_DEF)
      expect(await axe(container, axeTabRules)).toHaveNoViolations()
    })

    it('has no violations with close button', async () => {
      const { container } = renderPanelWithClose(vi.fn(), 'Most recent run details')
      expect(await axe(container, axeTabRules)).toHaveNoViolations()
    })
  })
})
