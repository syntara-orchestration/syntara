import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { ActivityState } from '../workflows/execution/types'

import { CompactActivityList } from './CompactActivityList'
import type { ActivityOrderItem } from './ExecutionActivityTable'

vi.mock('./ExecutionStatus', () => ({
  ActivityStatusLabel: ({ status }: { status: string }) => <span>{status}</span>,
}))

function state(id: string, overrides: Partial<ActivityState> = {}): [string, ActivityState] {
  return [id, { activityId: id, status: 'pending', ...overrides }]
}

const order: ActivityOrderItem[] = [{ id: 'task-1', name: 'Fetch Data' }, { id: 'task-2' }]

const states = new Map([
  state('task-1', { status: 'completed', startedAt: '2024-01-01T00:00:00Z', completedAt: '2024-01-01T00:01:00Z' }),
  state('task-2', { status: 'failed' }),
])

describe('CompactActivityList', () => {
  it('renders activity names, falling back to ID', () => {
    render(<CompactActivityList activityStates={states} activityOrder={order} />)

    expect(screen.getByText('Fetch Data')).toBeInTheDocument()
    expect(screen.getByText('task-2')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Activity list' })).toHaveClass('pf-m-compact')
  })

  it('renders status for each activity', () => {
    render(<CompactActivityList activityStates={states} activityOrder={order} />)

    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('includes activity title and status in each row accessible name', () => {
    render(<CompactActivityList activityStates={states} activityOrder={order} onRowClick={vi.fn()} />)

    const list = screen.getByRole('list', { name: 'Activity list' })
    expect(within(list).getByRole('listitem', { name: 'Fetch Data, Successful' })).toBeInTheDocument()
    expect(within(list).getByRole('listitem', { name: 'task-2, Failed' })).toBeInTheDocument()
  })

  it('shows time range when activity has start and end times', () => {
    render(<CompactActivityList activityStates={states} activityOrder={order} />)

    const timeElements = screen.getAllByText((_, el) => {
      if (el?.tagName !== 'SMALL') return false
      return el.textContent?.includes(' - ') ?? false
    })
    expect(timeElements.length).toBeGreaterThan(0)
  })

  it('calls onRowClick with node id and name when row is clicked', async () => {
    const user = userEvent.setup()
    const onRowClick = vi.fn()

    render(<CompactActivityList activityStates={states} activityOrder={order} onRowClick={onRowClick} />)

    await user.click(screen.getByText('Fetch Data'))
    expect(onRowClick).toHaveBeenCalledWith('task-1', 'Fetch Data')
  })

  it('calls onRowClick with id as name when name is not provided', async () => {
    const user = userEvent.setup()
    const onRowClick = vi.fn()

    render(<CompactActivityList activityStates={states} activityOrder={order} onRowClick={onRowClick} />)

    await user.click(screen.getByText('task-2'))
    expect(onRowClick).toHaveBeenCalledWith('task-2', 'task-2')
  })

  it('highlights selected row', () => {
    render(
      <CompactActivityList activityStates={states} activityOrder={order} selectedNodeId="task-1" onRowClick={vi.fn()} />
    )

    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveClass('pf-m-selected')
    expect(items[1]).not.toHaveClass('pf-m-selected')
  })

  it('highlights only the selected loop iteration', () => {
    const loopOrder: ActivityOrderItem[] = [
      { id: 'task-1', name: 'Fetch Data (iter 0)' },
      { id: 'task-1#iter-1', name: 'Fetch Data (iter 1)' },
      { id: 'task-1#iter-2', name: 'Fetch Data (iter 2)' },
    ]

    render(
      <CompactActivityList
        activityStates={new Map(loopOrder.map(({ id }) => state(id)))}
        activityOrder={loopOrder}
        selectedNodeId="task-1#iter-1"
        onRowClick={vi.fn()}
      />
    )

    const items = screen.getAllByRole('listitem')
    expect(items[0]).not.toHaveClass('pf-m-selected')
    expect(items[1]).toHaveClass('pf-m-selected')
    expect(items[2]).not.toHaveClass('pf-m-selected')
  })

  it('shows pending status when activity state is missing', () => {
    const emptyStates = new Map<string, ActivityState>()
    render(<CompactActivityList activityStates={emptyStates} activityOrder={[{ id: 'x', name: 'X' }]} />)

    expect(screen.getByText('pending')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <CompactActivityList activityStates={states} activityOrder={order} onRowClick={vi.fn()} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('uses selection when onRowClick is provided', () => {
    render(<CompactActivityList activityStates={states} activityOrder={order} onRowClick={vi.fn()} />)

    const list = screen.getByRole('list', { name: 'Activity list' })
    const firstItem = within(list).getAllByRole('listitem')[0]
    expect(firstItem).toHaveAttribute('tabindex', '0')
  })
})
