import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { ActivityState } from '../workflows/execution/types'

import { ExecutionActivityTable, type ActivityOrderItem } from './ExecutionActivityTable'

vi.mock('./ExecutionStatus', () => ({
  ActivityStatusLabel: ({ status }: { status: string }) => <div data-testid="activity-status-label">{status}</div>,
}))

const T0 = '2024-01-01T00:00:00Z'
const T2 = '2024-01-01T00:01:00Z'
const NOW = Date.parse('2024-01-01T00:02:00Z')

function state(id: string, overrides: Partial<ActivityState> = {}): [string, ActivityState] {
  return [id, { activityId: id, status: 'pending', ...overrides }]
}

function renderTable({
  states = new Map<string, ActivityState>(),
  order = [],
}: {
  states?: Map<string, ActivityState>
  order?: ActivityOrderItem[]
} = {}) {
  return render(<ExecutionActivityTable activityStates={states} activityOrder={order} now={NOW} />)
}

describe('ExecutionActivityTable', () => {
  describe('activity rows', () => {
    it('renders name, or falls back to activity ID', () => {
      renderTable({
        states: new Map([state('task-1'), state('task-2')]),
        order: [{ id: 'task-1', name: 'Process data' }, { id: 'task-2' }],
      })

      expect(screen.getByText('Process data')).toBeInTheDocument()
      expect(screen.getByText('task-2')).toBeInTheDocument()
    })

    it('shows formatted dates and elapsed for completed activity', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'completed', startedAt: T0, completedAt: T2 })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })

      expect(screen.getByText('1m 0s')).toBeInTheDocument()
    })

    it('shows dashes for pending activity', () => {
      renderTable({
        states: new Map([state('task-1')]),
        order: [{ id: 'task-1', name: 'Task' }],
      })

      expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3)
    })

    it('shows live elapsed for running activity', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'running', startedAt: T0 })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })

      expect(screen.getByText('2m 0s')).toBeInTheDocument()
    })

    it('renders correct status per row', () => {
      renderTable({
        states: new Map([state('a', { status: 'completed' }), state('b', { status: 'failed' })]),
        order: [
          { id: 'a', name: 'A' },
          { id: 'b', name: 'B' },
        ],
      })

      const labels = screen.getAllByTestId('activity-status-label')
      expect(labels[0]).toHaveTextContent('completed')
      expect(labels[1]).toHaveTextContent('failed')
    })
  })

  describe('error details', () => {
    it('shows error message below a failed activity', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'failed', errorDetails: 'HTTP 403: Forbidden' })]),
        order: [{ id: 'task-1', name: 'Fetch data' }],
      })

      expect(screen.getByText('HTTP 403: Forbidden')).toBeInTheDocument()
    })

    it('does not show error row when errorDetails is absent', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'completed' })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })

      expect(screen.queryByText('HTTP 403: Forbidden')).not.toBeInTheDocument()
    })
  })

  describe('AAP job link column', () => {
    it('shows AAP link column when workflow has AAP steps', () => {
      renderTable({
        states: new Map([
          state('aap-1', {
            status: 'running',
            outputData: { job_url: 'https://aap.example.com/execution/jobs/playbook/123/output' },
          }),
        ]),
        order: [{ id: 'aap-1', name: 'Launch job', type: 'aap_job_template' }],
      })

      const link = screen.getByRole('link', { name: /View job in AAP/i })
      expect(link).toHaveAttribute('href', 'https://aap.example.com/execution/jobs/playbook/123/output')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    })

    it('hides AAP column when no AAP steps exist', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'completed' })]),
        order: [{ id: 'task-1', name: 'Script step', type: 'script' }],
      })

      expect(screen.queryByRole('link', { name: /View job in AAP/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('columnheader', { name: 'AAP job link' })).not.toBeInTheDocument()
    })

    it('shows empty cell for non-AAP rows when column is visible', () => {
      renderTable({
        states: new Map([
          state('task-1'),
          state('aap-1', { status: 'running', outputData: { job_url: 'https://aap.example.com/j/1' } }),
        ]),
        order: [
          { id: 'task-1', name: 'Script', type: 'script' },
          { id: 'aap-1', name: 'AAP Job', type: 'aap_job_template' },
        ],
      })

      const links = screen.getAllByRole('link', { name: /View job in AAP/i })
      expect(links).toHaveLength(1)
    })

    it('shows no link when AAP activity has no output yet', () => {
      renderTable({
        states: new Map([state('aap-1', { status: 'running' })]),
        order: [{ id: 'aap-1', name: 'Launch job', type: 'aap_job_template' }],
      })

      expect(screen.queryByRole('link', { name: /View job in AAP/i })).not.toBeInTheDocument()
    })
  })

  describe('elapsed time computation', () => {
    it('returns elapsed ms for a completed activity', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'completed', startedAt: T0, completedAt: T2 })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })
      // T0→T2 is 60 seconds
      expect(screen.getByText('1m 0s')).toBeInTheDocument()
    })

    it('returns live elapsed for a running activity using now', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'running', startedAt: T0 })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })
      // T0→NOW is 120 seconds
      expect(screen.getByText('2m 0s')).toBeInTheDocument()
    })

    it('returns live elapsed for a retrying activity', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'retrying', startedAt: T0 })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })
      expect(screen.getByText('2m 0s')).toBeInTheDocument()
    })

    it('shows dash when activity has no startedAt', () => {
      renderTable({
        states: new Map([state('task-1', { status: 'pending' })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })
      // No start time → elapsed is undefined → dash rendered
      expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('accessibility', () => {
    it('renders original column headers without sort controls', () => {
      renderTable()

      expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Started' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Ended' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Elapsed time' })).toBeInTheDocument()
      expect(screen.getByRole('columnheader', { name: 'Status' })).toBeInTheDocument()
      expect(screen.getByRole('grid', { name: 'Activity states' })).toHaveClass('pf-m-compact')
      // Type column was removed — activities execute in chronological order
      expect(screen.queryByRole('columnheader', { name: 'Type' })).not.toBeInTheDocument()
    })

    it('has no accessibility violations', async () => {
      const { container } = renderTable({
        states: new Map([state('task-1', { status: 'completed', startedAt: T0, completedAt: T2 })]),
        order: [{ id: 'task-1', name: 'Task' }],
      })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
