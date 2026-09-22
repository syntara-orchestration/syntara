import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ExecutionDetailsPanel, type WorkflowDefShape } from './ExecutionDetailsPanel'

const WORKFLOW_DEF: WorkflowDefShape = {
  nodes: [
    { id: 'restart_service', name: 'Restart Service' },
    { id: 'was_restart_allowed', name: 'Was restart allowed' },
  ],
}

const { mockUseQuery } = vi.hoisted(() => ({ mockUseQuery: vi.fn() }))

vi.mock('../../client', () => ({
  executionsClient: { useQuery: mockUseQuery },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../hooks/routing/useSearchParams', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

const DENIED_EXECUTION = {
  id: 'exec-denied',
  workflow_id: 'wf-1',
  workflow_version_id: 'wfv-1',
  temporal_workflow_id: 'temporal-1',
  status: 'completed_with_errors',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:02:00Z',
  created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1', type: 'user' },
  updated_by: null,
  completed_at: '2024-01-01T00:02:00Z',
  input_data: {},
  error_details: null,
  denied_nodes: [{ node_id: 'restart_service', kind: 'http_request', denied_by: 'no-restarts-in-production' }],
  activities: [
    {
      activity_id: 'restart_service',
      status: 'denied',
      started_at: '2024-01-01T00:00:00Z',
      completed_at: '2024-01-01T00:00:00Z',
      error_details: '{"code": "node_execute_denied", "denied_by": "no-restarts-in-production"}',
    },
    {
      activity_id: 'was_restart_allowed',
      status: 'completed',
      started_at: '2024-01-01T00:00:01Z',
      completed_at: '2024-01-01T00:00:02Z',
    },
  ],
}

function mockExecution(execution: Record<string, unknown>) {
  mockUseQuery.mockReturnValue({ data: execution, isLoading: false, error: null, refetch: vi.fn() })
}

describe('ExecutionDetailsPanel — denied nodes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the "Denied nodes" section with the node name, kind and policy', () => {
    mockExecution(DENIED_EXECUTION)

    render(<ExecutionDetailsPanel executionId="exec-denied" workflowDefinition={WORKFLOW_DEF} />)

    const alert = within(screen.getByTestId('denied-nodes-alert'))
    expect(alert.getByText('Restart Service')).toBeInTheDocument()
    expect(alert.getByText('http_request')).toBeInTheDocument()
    expect(alert.getByText('Denied by policy "no-restarts-in-production"')).toBeInTheDocument()
  })

  it('renders the denied activity status as "Denied"', () => {
    mockExecution(DENIED_EXECUTION)

    render(<ExecutionDetailsPanel executionId="exec-denied" workflowDefinition={WORKFLOW_DEF} />)

    expect(screen.getByText('Denied')).toBeInTheDocument()
  })

  it('renders the node denial error as a readable sentence instead of raw JSON', () => {
    mockExecution(DENIED_EXECUTION)

    render(<ExecutionDetailsPanel executionId="exec-denied" workflowDefinition={WORKFLOW_DEF} />)

    expect(
      screen.getByText(
        'This step was not allowed to run for this execution. Denied by policy "no-restarts-in-production".'
      )
    ).toBeInTheDocument()
    expect(screen.queryByText(/node_execute_denied/)).not.toBeInTheDocument()
  })

  it('does not render a failure alert for a denied-only run', () => {
    mockExecution(DENIED_EXECUTION)

    render(<ExecutionDetailsPanel executionId="exec-denied" workflowDefinition={WORKFLOW_DEF} />)

    expect(screen.queryByText('Execution failed')).not.toBeInTheDocument()
  })

  it('renders no denied section when denied_nodes is absent', () => {
    mockExecution({ ...DENIED_EXECUTION, denied_nodes: null })

    render(<ExecutionDetailsPanel executionId="exec-denied" workflowDefinition={WORKFLOW_DEF} />)

    expect(screen.queryByTestId('denied-nodes-alert')).not.toBeInTheDocument()
  })
})
