import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SubWorkflowChildActivities } from './SubWorkflowChildActivities'

const mockUseQuery = vi.fn()

vi.mock('../../../client', () => ({
  executionsClient: {
    useQuery: (...args: unknown[]): unknown => mockUseQuery(...args),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

const CHILDREN = '/executions/{execution_id}/children'
const ACTIVITIES = '/executions/{execution_id}/activities'

const child = {
  id: 'exec-nested-leaf-001',
  workflow_name: 'Notification Dispatch (Nested Leaf)',
  workflow_version: 3,
  status: 'completed',
}

const activities = {
  resources: [
    {
      id: 'act-1',
      activity_name: 'format_message',
      node_type: 'script',
      status: 'completed',
      started_at: '2026-08-04T12:00:04.000Z',
      completed_at: '2026-08-04T12:00:05.000Z',
      output_data: { message: 'Platform alert escalated', channel: '#platform-alerts' },
    },
    {
      id: 'act-2',
      activity_name: 'send_notification',
      node_type: 'http_request',
      status: 'completed',
      started_at: '2026-08-04T12:00:05.000Z',
      completed_at: '2026-08-04T12:00:06.000Z',
      output_data: { delivery_id: 'del-nested-001', status: 'sent' },
    },
  ],
}

function setQueries(options: {
  children?: { data?: unknown; isLoading?: boolean; isError?: boolean }
  activities?: { data?: unknown; isLoading?: boolean; isError?: boolean }
}) {
  const { children: childrenQuery, activities: activitiesQuery } = options
  mockUseQuery.mockImplementation((_method: string, path: string) => {
    if (path === CHILDREN) {
      return { data: undefined, isLoading: false, isError: false, ...childrenQuery }
    }
    if (path === ACTIVITIES) {
      return { data: undefined, isLoading: false, isError: false, ...activitiesQuery }
    }
    return { data: undefined, isLoading: false, isError: false }
  })
}

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

function renderPanel() {
  return render(<SubWorkflowChildActivities parentExecutionId="parent-1" nodeId="sub_wf_node" />, { wrapper })
}

describe('SubWorkflowChildActivities', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a loading state while children load', () => {
    setQueries({ children: { isLoading: true } })
    renderPanel()
    expect(screen.getByLabelText('Loading child executions')).toBeInTheDocument()
  })

  it('shows an error state when the children lookup fails', () => {
    setQueries({ children: { isError: true } })
    renderPanel()
    expect(screen.getByText("Couldn't load the child execution(s).")).toBeInTheDocument()
  })

  it('shows an empty state when there are no children yet', () => {
    setQueries({ children: { data: { resources: [] } } })
    renderPanel()
    expect(screen.getByText('No child execution yet')).toBeInTheDocument()
  })

  it('renders child metadata, a navigation link, and child activities', async () => {
    setQueries({ children: { data: { resources: [child] } }, activities: { data: activities } })
    renderPanel()

    expect(screen.getByText('Notification Dispatch (Nested Leaf)')).toBeInTheDocument()
    expect(screen.getByText('v3')).toBeInTheDocument()
    expect(screen.getByText('Execution ID: exec-nested-leaf-001')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /View child execution/i }))
    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/executions/$executionId',
      params: { executionId: 'exec-nested-leaf-001' },
    })

    expect(screen.getByText('format_message')).toBeInTheDocument()
    expect(screen.getByText('send_notification')).toBeInTheDocument()

    // Each activity's real, distinct output_data is behind its expandable row.
    await userEvent.click(screen.getByText('format_message'))
    expect(screen.getByText(/Platform alert escalated/)).toBeInTheDocument()
    expect(screen.getByText(/#platform-alerts/)).toBeInTheDocument()

    await userEvent.click(screen.getByText('send_notification'))
    expect(screen.getByText(/del-nested-001/)).toBeInTheDocument()
  })

  it('handles an activity with no output_data', async () => {
    const noOutputActivities = {
      resources: [
        {
          id: 'act-x',
          activity_name: 'noop_step',
          node_type: 'script',
          status: 'completed',
          started_at: '2026-08-04T12:00:04.000Z',
          completed_at: '2026-08-04T12:00:05.000Z',
          output_data: null,
        },
      ],
    }
    setQueries({ children: { data: { resources: [child] } }, activities: { data: noOutputActivities } })
    renderPanel()

    await userEvent.click(screen.getByText('noop_step'))
    expect(screen.getByText('No output for this activity.')).toBeInTheDocument()
  })

  it('renders one section per child for a for_each sub-workflow', () => {
    const second = { ...child, id: 'exec-nested-leaf-002' }
    setQueries({ children: { data: { resources: [child, second] } }, activities: { data: { resources: [] } } })
    renderPanel()

    const buttons = screen.getAllByRole('button', { name: /View child execution/i })
    expect(buttons).toHaveLength(2)
  })

  it('shows error_details for a failed child activity instead of only "No output"', async () => {
    const failed = {
      resources: [
        {
          id: 'f1',
          activity_name: 'risky_step',
          node_type: 'script',
          status: 'failed',
          started_at: '2026-08-04T12:00:04.000Z',
          completed_at: '2026-08-04T12:00:05.000Z',
          output_data: null,
          error_details: 'Boom: connection refused',
        },
      ],
    }
    setQueries({ children: { data: { resources: [child] } }, activities: { data: failed } })
    renderPanel()

    await userEvent.click(screen.getByText('risky_step'))
    expect(screen.getByText('Error details')).toBeInTheDocument()
    expect(screen.getByText(/Boom: connection refused/)).toBeInTheDocument()
    expect(screen.queryByText('No output for this activity.')).not.toBeInTheDocument()
  })

  it('preserves output_data alongside error_details for a partially-failed activity', async () => {
    const failedWithOutput = {
      resources: [
        {
          id: 'f2',
          activity_name: 'partial_step',
          node_type: 'script',
          status: 'completed_with_errors',
          started_at: '2026-08-04T12:00:04.000Z',
          completed_at: '2026-08-04T12:00:05.000Z',
          output_data: { partial: 'kept' },
          error_details: 'a later step failed',
        },
      ],
    }
    setQueries({ children: { data: { resources: [child] } }, activities: { data: failedWithOutput } })
    renderPanel()

    await userEvent.click(screen.getByText('partial_step'))
    expect(screen.getByText(/a later step failed/)).toBeInTheDocument()
    expect(screen.getByText(/kept/)).toBeInTheDocument()
  })

  it('separates trigger activities under an expandable "Invocation details" section', async () => {
    const withTrigger = {
      resources: [
        {
          id: 't1',
          activity_name: 'child_in',
          node_type: 'subworkflow_trigger',
          status: 'completed',
          output_data: { username: 'rohit' },
        },
        {
          id: 'a1',
          activity_name: 'build_greeting',
          node_type: 'script',
          status: 'completed',
          output_data: { stdout: 'Hello rohit' },
        },
      ],
    }
    setQueries({ children: { data: { resources: [child] } }, activities: { data: withTrigger } })
    renderPanel()

    expect(screen.getByText('build_greeting')).toBeInTheDocument()
    expect(screen.getByText('Invocation details')).toBeInTheDocument()

    await userEvent.click(screen.getByText('Invocation details'))
    await userEvent.click(screen.getByText('child_in'))
    expect(screen.getByText(/"username": "rohit"/)).toBeInTheDocument()
  })

  it('omits "Invocation details" when there are no trigger activities', () => {
    setQueries({ children: { data: { resources: [child] } }, activities: { data: activities } })
    renderPanel()

    expect(screen.queryByText('Invocation details')).not.toBeInTheDocument()
  })

  it('requests up to 100 child executions and child activities to avoid silent truncation', () => {
    setQueries({ children: { data: { resources: [child] } }, activities: { data: activities } })
    renderPanel()

    const calls = mockUseQuery.mock.calls as unknown[][]
    const childrenOpts = calls.find((c) => c[1] === CHILDREN)?.[2] as
      { params?: { query?: { limit?: number } } } | undefined
    const activitiesOpts = calls.find((c) => c[1] === ACTIVITIES)?.[2] as
      { params?: { query?: { limit?: number } } } | undefined

    expect(childrenOpts?.params?.query?.limit).toBe(100)
    expect(activitiesOpts?.params?.query?.limit).toBe(100)
  })
})
