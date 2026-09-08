import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import type { AgentTrace } from './agentTraceTypes'
import { extractAgentTrace } from './agentTraceTypes'
import { AgentTraceView } from './AgentTraceView'

const sampleTrace: AgentTrace = {
  model: 'anthropic/claude-haiku-4.5',
  total_tokens: 500,
  total_duration_ms: 2000,
  steps: [
    {
      type: 'reasoning',
      timestamp: '2026-07-08T17:00:00Z',
      content: 'Analyzing the incident to identify affected hosts.',
      tokens: 100,
      duration_ms: 400,
    },
    {
      type: 'tool_call',
      timestamp: '2026-07-08T17:00:01Z',
      content: 'Querying Splunk for error logs',
      tool_name: 'Splunk Query',
      tool_input: { query: 'index=prod level=ERROR', max_results: 50 },
      tokens: 80,
    },
    {
      type: 'tool_result',
      timestamp: '2026-07-08T17:00:02Z',
      content: 'Found 47 error events across 3 hosts.',
      tool_name: 'Splunk Query',
      tool_output: 'Found 47 error events. Top hosts: web1, web2, web3.',
      duration_ms: 800,
    },
    {
      type: 'reasoning',
      timestamp: '2026-07-08T17:00:03Z',
      content: 'The evidence shows all hosts need patching.',
      tokens: 120,
      duration_ms: 350,
    },
    {
      type: 'final_answer',
      timestamp: '2026-07-08T17:00:04Z',
      content: 'Analysis complete. 3 hosts require critical patches.',
    },
  ],
}

describe('AgentTraceView', () => {
  it('renders header stats from trace data', () => {
    render(<AgentTraceView agentTrace={sampleTrace} />)

    expect(screen.getByText('anthropic/claude-haiku-4.5')).toBeInTheDocument()
    expect(screen.getByText('500')).toBeInTheDocument()
    expect(screen.getByText('Trace time')).toBeInTheDocument()
    expect(screen.getByText('2.0s')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('renders reasoning and final answer type labels', () => {
    render(<AgentTraceView agentTrace={sampleTrace} />)

    expect(screen.getAllByText('Reasoning')).toHaveLength(2)
    expect(screen.getByText('Final answer')).toBeInTheDocument()
  })

  it('renders reasoning blocks', () => {
    render(<AgentTraceView agentTrace={sampleTrace} />)

    expect(screen.getByText('Analyzing the incident to identify affected hosts.')).toBeInTheDocument()
    expect(screen.getByText('The evidence shows all hosts need patching.')).toBeInTheDocument()
  })

  it('renders tool call card with tool name', () => {
    render(<AgentTraceView agentTrace={sampleTrace} />)

    expect(screen.getByText('Splunk Query')).toBeInTheDocument()
    expect(screen.getByText('Querying Splunk for error logs')).toBeInTheDocument()
  })

  it('renders tool result response via SynDetail', () => {
    render(<AgentTraceView agentTrace={sampleTrace} />)

    expect(screen.getByText('Request')).toBeInTheDocument()
    expect(screen.getByText('Response')).toBeInTheDocument()
    expect(screen.getByText('Found 47 error events. Top hosts: web1, web2, web3.')).toBeInTheDocument()
  })

  it('renders final answer block', () => {
    render(<AgentTraceView agentTrace={sampleTrace} />)

    expect(screen.getByText('Analysis complete. 3 hosts require critical patches.')).toBeInTheDocument()
  })

  it('renders structured response-schema final answer as key/value fields', () => {
    const trace = extractAgentTrace({
      agent_trace: {
        model: 'test-model',
        total_tokens: 10,
        total_duration_ms: 100,
        steps: [
          {
            type: 'final_answer',
            timestamp: '2026-01-01T00:00:00Z',
            content: {
              incident_id: 'INC-4520',
              severity: 'high',
              summary: 'SSL incident triage',
              impacted_hosts: ['web1.example.com', 'web2.example.com'],
            },
          },
        ],
      },
    })

    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('Final answer')).toBeInTheDocument()
    expect(screen.getByText('incident id')).toBeInTheDocument()
    expect(screen.getByText('INC-4520')).toBeInTheDocument()
    expect(screen.getByText('severity')).toBeInTheDocument()
    expect(screen.getByText('high')).toBeInTheDocument()
    expect(screen.getByText('SSL incident triage')).toBeInTheDocument()
    expect(screen.getByText('web1.example.com')).toBeInTheDocument()
    expect(screen.getByText('web2.example.com')).toBeInTheDocument()
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('JSON')).toBeInTheDocument()
    expect(screen.getByText(/"incident_id": "INC-4520"/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy to clipboard' })).toBeInTheDocument()
  })

  it('renders structured response-schema reasoning as key/value fields', () => {
    const trace = extractAgentTrace({
      agent_trace: {
        model: 'test-model',
        total_tokens: 10,
        total_duration_ms: 100,
        steps: [
          {
            type: 'reasoning',
            timestamp: '2026-01-01T00:00:00Z',
            content: {
              status: 'investigating',
              note: 'Gathering host inventory',
            },
          },
        ],
      },
    })

    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('Reasoning')).toBeInTheDocument()
    expect(screen.getByText('status')).toBeInTheDocument()
    expect(screen.getByText('investigating')).toBeInTheDocument()
    expect(screen.getByText('note')).toBeInTheDocument()
    expect(screen.getByText('Gathering host inventory')).toBeInTheDocument()
    expect(screen.getByText('JSON')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy to clipboard' })).toBeInTheDocument()
  })

  it('has no accessibility violations for structured response-schema content', async () => {
    const trace = extractAgentTrace({
      agent_trace: {
        model: 'test-model',
        total_tokens: 10,
        total_duration_ms: 100,
        steps: [
          {
            type: 'final_answer',
            timestamp: '2026-01-01T00:00:00Z',
            content: {
              incident_id: 'INC-4520',
              severity: 'high',
              summary: 'SSL incident triage',
              impacted_hosts: ['web1.example.com', 'web2.example.com'],
            },
          },
        ],
      },
    })

    const { container } = render(<AgentTraceView agentTrace={trace} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('shows empty state when no trace', () => {
    render(<AgentTraceView agentTrace={null} />)

    expect(screen.getByText('No agent steps yet')).toBeInTheDocument()
  })

  it('shows empty state when trace has empty steps', () => {
    render(<AgentTraceView agentTrace={{ model: 'test', total_tokens: 0, total_duration_ms: 0, steps: [] }} />)

    expect(screen.getByText('No agent steps yet')).toBeInTheDocument()
  })

  it('shows loading spinner', () => {
    render(<AgentTraceView agentTrace={null} isLoading />)

    expect(screen.getByRole('progressbar', { name: 'Loading agent trace' })).toBeInTheDocument()
  })

  it('prioritizes loading state even when trace data exists', () => {
    render(<AgentTraceView agentTrace={sampleTrace} isLoading />)

    expect(screen.getByRole('progressbar', { name: 'Loading agent trace' })).toBeInTheDocument()
    expect(screen.queryByRole('log', { name: 'Agent reasoning steps' })).not.toBeInTheDocument()
  })

  it('renders expandable tool input section', async () => {
    const user = userEvent.setup()
    render(<AgentTraceView agentTrace={sampleTrace} />)

    const toggleButton = screen.getByRole('button', { name: /show input/i })
    await user.click(toggleButton)

    expect(screen.getByText(/"query": "index=prod level=ERROR"/)).toBeInTheDocument()
  })

  it('toggles tool input section open and closed', async () => {
    const user = userEvent.setup()
    render(<AgentTraceView agentTrace={sampleTrace} />)

    const toggleButton = screen.getByRole('button', { name: /show input/i })
    await user.click(toggleButton)
    expect(screen.getByRole('button', { name: /hide input/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /hide input/i }))
    expect(screen.getByRole('button', { name: /show input/i })).toBeInTheDocument()
  })

  it('shows Failed label for failed tool calls', () => {
    const traceWithFailure: AgentTrace = {
      model: 'test-model',
      total_tokens: 100,
      total_duration_ms: 500,
      steps: [
        {
          type: 'tool_call',
          timestamp: '2026-07-08T17:00:00Z',
          content: 'Calling broken tool',
          tool_name: 'Broken Tool',
          tool_input: {},
        },
        {
          type: 'tool_result',
          timestamp: '2026-07-08T17:00:01Z',
          content: 'Connection refused',
          tool_name: 'Broken Tool',
          tool_output: 'Connection refused',
          status: 'failed',
        },
      ],
    }
    render(<AgentTraceView agentTrace={traceWithFailure} />)

    expect(screen.getByText('Failed', { selector: '.pf-v6-c-label__text' })).toBeInTheDocument()
    expect(screen.getByText('Broken Tool')).toBeInTheDocument()
  })

  it('does not render orphan tool_result steps that bypass grouping', () => {
    const traceWithOrphanResult: AgentTrace = {
      model: 'test',
      total_tokens: 10,
      total_duration_ms: 100,
      steps: [
        {
          type: 'tool_result',
          timestamp: '2026-07-08T17:00:00Z',
          content: 'orphan result',
          tool_name: 'x',
          tool_output: 'data',
        },
      ],
    }
    render(<AgentTraceView agentTrace={traceWithOrphanResult} />)
    expect(screen.getByRole('log')).toBeInTheDocument()
  })

  it('has role="log" on the steps list for accessibility', () => {
    render(<AgentTraceView agentTrace={sampleTrace} />)

    expect(screen.getByRole('log', { name: 'Agent reasoning steps' })).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<AgentTraceView agentTrace={sampleTrace} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations when empty', async () => {
    const { container } = render(<AgentTraceView agentTrace={null} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders reasoning block without metrics when tokens and duration are absent', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 0,
      total_duration_ms: 0,
      steps: [{ type: 'reasoning', timestamp: '2026-01-01T00:00:00Z', content: 'Thinking...' }],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('Thinking...')).toBeInTheDocument()
    expect(screen.queryByText(/tokens/)).not.toBeInTheDocument()
  })

  it('renders duration in milliseconds when under 1 second', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 10,
      total_duration_ms: 450,
      steps: [
        { type: 'reasoning', timestamp: '2026-01-01T00:00:00Z', content: 'Quick thought', tokens: 5, duration_ms: 200 },
      ],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('450ms')).toBeInTheDocument()
    expect(screen.getByText('5 tokens · 200ms')).toBeInTheDocument()
  })

  it('renders tool card without metrics when tokens and duration are absent', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 0,
      total_duration_ms: 0,
      steps: [
        {
          type: 'tool_call',
          timestamp: '2026-01-01T00:00:00Z',
          content: 'Calling tool',
          tool_name: 'my_tool',
          tool_input: {},
        },
        {
          type: 'tool_result',
          timestamp: '2026-01-01T00:00:01Z',
          content: 'Result',
          tool_name: 'my_tool',
          tool_output: 'done',
          status: 'success',
        },
      ],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('my_tool')).toBeInTheDocument()
    expect(screen.queryByText(/tokens/)).not.toBeInTheDocument()
  })

  it('renders successful tool card without Failed label', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 50,
      total_duration_ms: 500,
      steps: [
        {
          type: 'tool_call',
          timestamp: '2026-01-01T00:00:00Z',
          content: 'Calling tool',
          tool_name: 'good_tool',
          tool_input: { q: 'test' },
          tokens: 10,
          call_id: 'call-0',
        },
        {
          type: 'tool_result',
          timestamp: '2026-01-01T00:00:01Z',
          content: 'OK',
          tool_name: 'good_tool',
          tool_output: 'Success',
          status: 'success',
          call_id: 'call-0',
          duration_ms: 50,
        },
      ],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('good_tool')).toBeInTheDocument()
    expect(screen.queryByText('Failed')).not.toBeInTheDocument()
    expect(screen.getByText('10 tokens · 50ms')).toBeInTheDocument()
  })

  it('renders final answer with metrics when tokens are present', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 100,
      total_duration_ms: 2000,
      steps: [
        { type: 'final_answer', timestamp: '2026-01-01T00:00:00Z', content: 'Done.', tokens: 30, duration_ms: 1500 },
      ],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('Done.')).toBeInTheDocument()
    expect(screen.getByText('30 tokens · 1.5s')).toBeInTheDocument()
  })

  it('uses toolName as key fallback when callId is absent', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 0,
      total_duration_ms: 0,
      steps: [
        {
          type: 'tool_call',
          timestamp: '2026-01-01T00:00:00Z',
          content: 'Call',
          tool_name: 'fallback_tool',
          tool_input: {},
        },
        {
          type: 'tool_result',
          timestamp: '2026-01-01T00:00:01Z',
          content: 'OK',
          tool_name: 'fallback_tool',
          tool_output: 'result',
        },
      ],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('fallback_tool')).toBeInTheDocument()
  })

  it('renders metrics with only tokens when duration is absent', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 50,
      total_duration_ms: 1000,
      steps: [{ type: 'reasoning', timestamp: '2026-01-01T00:00:00Z', content: 'Thought', tokens: 25 }],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('25 tokens')).toBeInTheDocument()
  })

  it('renders metrics with only duration when tokens are absent', () => {
    const trace: AgentTrace = {
      model: 'test',
      total_tokens: 0,
      total_duration_ms: 1000,
      steps: [{ type: 'reasoning', timestamp: '2026-01-01T00:00:00Z', content: 'Thought', duration_ms: 750 }],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('750ms')).toBeInTheDocument()
  })

  it('renders zero tool calls in header when there are no tool steps', () => {
    const trace: AgentTrace = {
      model: 'test-model',
      total_tokens: 1234,
      total_duration_ms: 1200,
      steps: [{ type: 'reasoning', timestamp: '2026-01-01T00:00:00Z', content: 'Only reasoning step' }],
    }
    render(<AgentTraceView agentTrace={trace} />)

    expect(screen.getByText('Tool calls')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.getByText('1,234')).toBeInTheDocument()
  })
})
