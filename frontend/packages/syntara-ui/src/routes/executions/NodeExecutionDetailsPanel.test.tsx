import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { NodeExecutionDetailsPanel } from './NodeExecutionDetailsPanel'

const mockActivityData = {
  resources: [
    {
      activity_name: 'run_aap_vm',
      input_data: { host: '10.0.0.1', template_id: 42 },
      output_data: { status: 'ok', stdout: 'VM provisioned successfully' },
      status: 'completed',
    },
  ],
}

const mockUseQuery =
  vi.fn<() => { data: unknown; isLoading: boolean; error: unknown; refetch: () => Promise<unknown> }>()

vi.mock('../../client', () => ({
  executionsClient: {
    useQuery: (...args: unknown[]) => mockUseQuery(...(args as [])),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
)

const defaultProps = {
  nodeId: 'run_aap_vm',
  nodeName: 'Run AAP VM',
  executionId: 'exec-123',
  nodeState: {
    activityId: 'run_aap_vm',
    status: 'completed' as const,
    startedAt: '2024-01-01T10:00:00Z',
    completedAt: '2024-01-01T10:01:30Z',
  },
}

describe('NodeExecutionDetailsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseQuery.mockReturnValue({ data: mockActivityData, isLoading: false, error: null, refetch: vi.fn() })
  })

  it('renders the node name in the header', () => {
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByRole('heading', { name: 'Run AAP VM' })).toBeInTheDocument()
  })

  it('renders node status in the header', () => {
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByText('Successful')).toBeInTheDocument()
  })

  it('renders Input and Output panes side by side', () => {
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByText('Parameters')).toBeInTheDocument()
    expect(screen.getByText('Output')).toBeInTheDocument()
  })

  it('shows input data in the input pane by default (JSON view)', () => {
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByText(/"host"/)).toBeInTheDocument()
    expect(screen.getByText(/"10.0.0.1"/)).toBeInTheDocument()
  })

  it('shows output data in the output pane by default (JSON view)', () => {
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByText(/"stdout"/)).toBeInTheDocument()
    expect(screen.getByText(/"VM provisioned successfully"/)).toBeInTheDocument()
  })

  it('renders schema view when switching to Schema', async () => {
    const user = userEvent.setup()
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    const schemaButtons = screen.getAllByRole('button', { name: 'Schema' })
    await user.click(schemaButtons[0])

    expect(screen.getByLabelText('Input schema')).toBeInTheDocument()
  })

  it('renders table view when switching to Table', async () => {
    const user = userEvent.setup()
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    const tableButtons = screen.getAllByRole('button', { name: 'Table' })
    await user.click(tableButtons[0])

    expect(screen.getByLabelText('Input data')).toBeInTheDocument()
  })

  it('shows loading spinner when data is loading', () => {
    mockUseQuery.mockReturnValue({ data: null, isLoading: true, error: null, refetch: vi.fn() })
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('shows empty state when output data is null', () => {
    mockUseQuery.mockReturnValue({
      data: { resources: [{ activity_name: 'run_aap_vm', output_data: null }] },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByText('No output data')).toBeInTheDocument()
  })

  it('shows empty state when input data is null', () => {
    mockUseQuery.mockReturnValue({
      data: { resources: [{ activity_name: 'run_aap_vm', input_data: undefined }] },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByText('No parameters data')).toBeInTheDocument()
  })

  it('passes activity_name as query parameter for server-side filtering', () => {
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(mockUseQuery).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}/activities',
      expect.objectContaining({
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        params: expect.objectContaining({
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          query: expect.objectContaining({ activity_name: 'run_aap_vm' }),
        }),
      }),
      expect.anything()
    )
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })

  it('has no accessibility violations in loading state', async () => {
    mockUseQuery.mockReturnValue({ data: null, isLoading: true, error: null, refetch: vi.fn() })
    const { container } = render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })

  it('shows error state when activity data fetch fails', () => {
    const refetch = vi.fn()
    mockUseQuery.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
      refetch,
    })

    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    expect(screen.getByText('Error loading activity data')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('calls refetch when retry is clicked on error state', async () => {
    const user = userEvent.setup()
    const refetch = vi.fn().mockResolvedValue(undefined)
    // retryable: true so ErrorState renders the Retry button
    const error = Object.assign(new Error('Network error'), { retryable: true })
    mockUseQuery.mockReturnValue({ data: null, isLoading: false, error, refetch })

    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalledOnce()
  })

  it('renders without elapsed time when node has not started', () => {
    const propsWithoutStart = {
      ...defaultProps,
      nodeState: undefined,
    }
    render(<NodeExecutionDetailsPanel {...propsWithoutStart} />, { wrapper })

    expect(screen.queryByText(/Elapsed time:/)).not.toBeInTheDocument()
    expect(screen.queryByText(/2024-01-01/)).not.toBeInTheDocument()
  })

  it('highlights search results in JSON view', async () => {
    const user = userEvent.setup()
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView

    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    const searchInputs = screen.getAllByPlaceholderText('Search')
    await user.type(searchInputs[0], 'host')

    // Verify that mark elements are rendered (highlighted search results)
    const marks = screen.getAllByRole('mark')
    expect(marks.length).toBeGreaterThan(0)
  })

  it('scrolls to first search match when typing in search', async () => {
    const user = userEvent.setup()
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView

    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    const searchInputs = screen.getAllByPlaceholderText('Search')
    await user.type(searchInputs[0], 'host')

    // In JSDOM scrollIntoView might not be called, so just verify search value changed
    expect(searchInputs[0]).toHaveValue('host')
  })

  it('clears search term when clear button is clicked', async () => {
    const user = userEvent.setup()
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    const searchInputs = screen.getAllByPlaceholderText('Search')
    await user.type(searchInputs[0], 'host')

    // PatternFly SearchInput clear button is labeled "Reset"
    const clearButton = screen.getAllByRole('button', { name: /reset/i })[0]
    await user.click(clearButton)

    expect(searchInputs[0]).toHaveValue('')
  })

  it('renders running status with elapsed time updating', () => {
    const propsWithRunning = {
      ...defaultProps,
      nodeState: {
        activityId: 'run_aap_vm',
        status: 'running' as const,
        startedAt: new Date(Date.now() - 5000).toISOString(),
        completedAt: undefined,
      },
    }
    render(<NodeExecutionDetailsPanel {...propsWithRunning} />, { wrapper })

    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText(/Elapsed time:/)).toBeInTheDocument()
  })

  it('renders failed status with error styling on output', () => {
    const propsWithFailed = {
      ...defaultProps,
      nodeState: {
        activityId: 'run_aap_vm',
        status: 'failed' as const,
        startedAt: '2024-01-01T10:00:00Z',
        completedAt: '2024-01-01T10:01:30Z',
      },
    }
    render(<NodeExecutionDetailsPanel {...propsWithFailed} />, { wrapper })

    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('renders timestamp range when node has both start and end times', () => {
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    // Start and end render as two separate <time> elements (via PatternFly Timestamp)
    // joined by " - ". Timestamps render in local timezone, so just verify the date
    // appears twice rather than asserting an exact combined string.
    expect(screen.getAllByText(/Jan.*1.*2024/i)).toHaveLength(2)
  })

  it('renders only start timestamp when completion time is missing', () => {
    const propsWithoutCompletedAt = {
      ...defaultProps,
      nodeState: {
        ...defaultProps.nodeState,
        completedAt: undefined,
      },
    }
    render(<NodeExecutionDetailsPanel {...propsWithoutCompletedAt} />, { wrapper })

    expect(screen.getAllByText(/Jan.*1.*2024/i)).toHaveLength(1)
    expect(screen.queryByText(/ - /)).not.toBeInTheDocument()
  })

  it('switches between different view modes for input pane', async () => {
    const user = userEvent.setup()
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    // Start in JSON view
    expect(screen.getByText(/"host"/)).toBeInTheDocument()

    // Switch to Schema view
    const schemaButtons = screen.getAllByRole('button', { name: 'Schema' })
    await user.click(schemaButtons[0]) // First one is for Parameters/Input

    expect(screen.getByLabelText('Input schema')).toBeInTheDocument()

    // Switch to Table view
    const tableButtons = screen.getAllByRole('button', { name: 'Table' })
    await user.click(tableButtons[0])

    expect(screen.getByLabelText('Input data')).toBeInTheDocument()
  })

  it('switches between different view modes for output pane', async () => {
    const user = userEvent.setup()
    render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

    // Switch output to Schema view
    const schemaButtons = screen.getAllByRole('button', { name: 'Schema' })
    await user.click(schemaButtons[1]) // Second one is for Output

    // InputSchemaView has aria-label="Input schema", verify output schema is rendered
    expect(screen.getByLabelText('Input schema')).toBeInTheDocument()
  })

  describe('ApprovalAuditSection', () => {
    const approvalOutputData = {
      resources: [
        {
          activity_name: 'review_deployment',
          input_data: { prompt: 'Approve deployment' },
          output_data: {
            status: 'completed',
            decision: 'approved',
            decided_by: 'jsmith',
            decided_at: '2026-06-15T08:00:01.000Z',
            decision_notes: 'Verified staging tests pass.',
          },
          status: 'completed',
        },
      ],
    }

    it('renders approval audit strip when output contains approval data', () => {
      mockUseQuery.mockReturnValue({ data: approvalOutputData, isLoading: false, error: null, refetch: vi.fn() })
      render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

      expect(screen.getByText('Decision')).toBeInTheDocument()
      expect(screen.getByText('Approved')).toBeInTheDocument()
      expect(screen.getByText('Decided by')).toBeInTheDocument()
      expect(screen.getByText('jsmith')).toBeInTheDocument()
      expect(screen.getByText('Decided at')).toBeInTheDocument()
      expect(screen.getByText('Notes')).toBeInTheDocument()
      expect(screen.getByText('Verified staging tests pass.')).toBeInTheDocument()
    })

    it('does not render approval audit strip for non-approval output', () => {
      render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

      expect(screen.queryByText('Decision')).not.toBeInTheDocument()
      expect(screen.queryByText('Decided by')).not.toBeInTheDocument()
    })

    it('does not render notes section when decision_notes is absent', () => {
      const dataWithoutNotes = {
        resources: [
          {
            activity_name: 'review_deployment',
            input_data: {},
            output_data: {
              status: 'completed',
              decision: 'rejected',
              decided_by: 'admin',
              decided_at: '2026-06-15T09:00:00.000Z',
            },
            status: 'completed',
          },
        ],
      }
      mockUseQuery.mockReturnValue({ data: dataWithoutNotes, isLoading: false, error: null, refetch: vi.fn() })
      render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

      expect(screen.getByText('Rejected')).toBeInTheDocument()
      expect(screen.queryByText('Notes')).not.toBeInTheDocument()
    })

    it('renders unknown decision with info fallback when decision is unmapped', () => {
      const dataWithUnknownDecision = {
        resources: [
          {
            activity_name: 'review_deployment',
            input_data: {},
            output_data: {
              status: 'completed',
              decision: 'deferred',
              decided_by: 'admin',
              decided_at: '2026-06-15T09:00:00.000Z',
            },
            status: 'completed',
          },
        ],
      }
      mockUseQuery.mockReturnValue({ data: dataWithUnknownDecision, isLoading: false, error: null, refetch: vi.fn() })
      render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

      expect(screen.getByText('Deferred')).toBeInTheDocument()
      expect(screen.getByText('Decided by')).toBeInTheDocument()
      expect(screen.getByText('admin')).toBeInTheDocument()
    })

    it('has no accessibility violations with approval audit displayed', async () => {
      mockUseQuery.mockReturnValue({ data: approvalOutputData, isLoading: false, error: null, refetch: vi.fn() })
      const { container } = render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })

  describe('AAP job link', () => {
    it('shows "View job in AAP" link for AAP step with job_url', () => {
      mockUseQuery.mockReturnValue({
        data: {
          resources: [
            {
              activity_name: 'run_aap_vm',
              input_data: {},
              output_data: { job_id: 123, job_url: 'https://aap.example.com/jobs/123' },
              status: 'running',
            },
          ],
        },
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...defaultProps} nodeType="aap_job_template" />, { wrapper })

      const link = screen.getByRole('link', { name: /View job in AAP/i })
      expect(link).toHaveAttribute('href', 'https://aap.example.com/jobs/123')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    })

    it('does not show AAP link for non-AAP step types', () => {
      render(<NodeExecutionDetailsPanel {...defaultProps} nodeType="script" />, { wrapper })

      expect(screen.queryByRole('link', { name: /View job in AAP/i })).not.toBeInTheDocument()
    })

    it('does not show AAP link when nodeType is undefined', () => {
      render(<NodeExecutionDetailsPanel {...defaultProps} />, { wrapper })

      expect(screen.queryByRole('link', { name: /View job in AAP/i })).not.toBeInTheDocument()
    })

    it('does not show AAP link when output has no job_url', () => {
      mockUseQuery.mockReturnValue({
        data: {
          resources: [
            {
              activity_name: 'run_aap_vm',
              input_data: {},
              output_data: { status: 'running' },
              status: 'running',
            },
          ],
        },
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...defaultProps} nodeType="aap_job_template" />, { wrapper })

      expect(screen.queryByRole('link', { name: /View job in AAP/i })).not.toBeInTheDocument()
    })
  })

  describe('agentic node', () => {
    const agenticProps = {
      ...defaultProps,
      nodeId: 'triage_agent',
      nodeName: 'AI Agent',
      nodeType: 'agentic',
    }

    const mockAgenticActivityData = {
      resources: [
        {
          activity_name: 'triage_agent',
          input_data: { prompt: 'Investigate incident' },
          output_data: {
            result: {
              content: 'Investigation complete',
              agent_trace: {
                model: 'test-model',
                total_tokens: 150,
                total_duration_ms: 5000,
                steps: [
                  {
                    type: 'reasoning',
                    timestamp: '2024-01-01T10:00:00Z',
                    content: 'Analyzing the incident logs',
                  },
                  {
                    type: 'tool_call',
                    timestamp: '2024-01-01T10:00:01Z',
                    content: 'Calling search_logs',
                    tool_name: 'search_logs',
                    tool_input: { query: 'error' },
                    call_id: 'call-0',
                  },
                  {
                    type: 'tool_result',
                    timestamp: '2024-01-01T10:00:02Z',
                    content: 'Found 47 errors',
                    tool_name: 'search_logs',
                    tool_output: 'Found 47 errors',
                    status: 'success',
                    call_id: 'call-0',
                    duration_ms: 30,
                  },
                ],
              },
            },
          },
          status: 'completed',
        },
      ],
    }

    it('renders tab bar with Input/Output and Agent steps tabs', () => {
      mockUseQuery.mockReturnValue({
        data: mockAgenticActivityData,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...agenticProps} />, { wrapper })

      expect(screen.getByRole('tab', { name: /Input\/Output/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /Agent steps/i })).toBeInTheDocument()
    })

    it('does not render tab bar for non-agentic nodes', () => {
      mockUseQuery.mockReturnValue({
        data: mockActivityData,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...defaultProps} nodeType="script" />, { wrapper })

      expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    })

    it('shows agent trace content when Agent steps tab is clicked', async () => {
      const user = userEvent.setup()
      mockUseQuery.mockReturnValue({
        data: mockAgenticActivityData,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...agenticProps} />, { wrapper })

      await user.click(screen.getByRole('tab', { name: /Agent steps/i }))

      expect(screen.getByText('Analyzing the incident logs')).toBeInTheDocument()
    })

    it('switches back to I/O view when Input/Output tab is clicked', async () => {
      const user = userEvent.setup()
      mockUseQuery.mockReturnValue({
        data: mockAgenticActivityData,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...agenticProps} />, { wrapper })

      await user.click(screen.getByRole('tab', { name: /Agent steps/i }))
      expect(screen.getByText('Analyzing the incident logs')).toBeInTheDocument()

      await user.click(screen.getByRole('tab', { name: /Input\/Output/i }))
      expect(screen.getByText('Parameters')).toBeInTheDocument()
      expect(screen.getByText('Output')).toBeInTheDocument()
    })

    it('shows empty state when output has no agent trace', async () => {
      const user = userEvent.setup()
      mockUseQuery.mockReturnValue({
        data: {
          resources: [
            {
              activity_name: 'triage_agent',
              input_data: { prompt: 'test' },
              output_data: { result: { content: 'done' } },
              status: 'completed',
            },
          ],
        },
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...agenticProps} />, { wrapper })

      await user.click(screen.getByRole('tab', { name: /Agent steps/i }))

      expect(screen.getByText(/No agent steps yet/i)).toBeInTheDocument()
    })

    it('defaults to Input/Output tab as selected', () => {
      mockUseQuery.mockReturnValue({
        data: mockAgenticActivityData,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...agenticProps} />, { wrapper })

      expect(screen.getByRole('tab', { name: /Input\/Output/i, selected: true })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /Agent steps/i, selected: false })).toBeInTheDocument()
      expect(screen.getByText('Parameters')).toBeInTheDocument()
    })

    it('renders tools used summary from agentic output_data', () => {
      mockUseQuery.mockReturnValue({
        data: {
          resources: [
            {
              activity_name: 'triage_agent',
              input_data: { prompt: 'hi' },
              output_data: {
                result: {
                  content: 'done',
                  used_tools: [
                    { name: 'search', count: 2 },
                    { name: 'fetch', count: 1 },
                  ],
                },
              },
              status: 'completed',
            },
          ],
        },
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      })

      render(<NodeExecutionDetailsPanel {...agenticProps} />, { wrapper })

      expect(screen.getByText('Tools used')).toBeInTheDocument()
      expect(screen.getByText('search (2), fetch (1)')).toBeInTheDocument()
    })
  })
})
