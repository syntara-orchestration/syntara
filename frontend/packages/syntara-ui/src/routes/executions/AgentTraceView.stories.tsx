import type { Meta, StoryObj } from '@storybook/tanstack-react'

import type { AgentTrace } from './agentTraceTypes'
import { AgentTraceView } from './AgentTraceView'

const meta: Meta<typeof AgentTraceView> = {
  component: AgentTraceView,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: 'Renders agent reasoning steps including reasoning blocks, tool call cards, and final answers.',
      },
    },
  },
}

export default meta
type Story = StoryObj<typeof AgentTraceView>

const fullTrace: AgentTrace = {
  model: 'anthropic/claude-haiku-4.5',
  total_tokens: 352,
  total_duration_ms: 9600,
  steps: [
    {
      type: 'reasoning',
      timestamp: '2026-07-13T18:27:40Z',
      content:
        "I'll investigate incident INC-4520. Let me search the logs for error patterns in the web-frontend service.",
      tokens: 33,
      duration_ms: 1184,
    },
    {
      type: 'tool_call',
      timestamp: '2026-07-13T18:27:41Z',
      content: 'Calling search_logs',
      tool_name: 'search_logs',
      tool_input: { query: 'error', service: 'web-frontend', hours: 4 },
      call_id: 'call-0',
    },
    {
      type: 'tool_result',
      timestamp: '2026-07-13T18:27:41Z',
      content: 'Found 47 error events across 3 hosts.',
      tool_name: 'search_logs',
      tool_output:
        'Found 47 error events. Top hosts: web1.example.com, web2.example.com, web3.example.com. Error pattern: "SSL_do_handshake() failed"',
      status: 'success',
      duration_ms: 31,
      call_id: 'call-0',
    },
    {
      type: 'reasoning',
      timestamp: '2026-07-13T18:27:43Z',
      content:
        '47 error events detected with SSL_do_handshake() failures. This indicates OpenSSL issues. Let me check the host configuration.',
      tokens: 41,
      duration_ms: 1200,
    },
    {
      type: 'tool_call',
      timestamp: '2026-07-13T18:27:44Z',
      content: 'Calling lookup_host_info',
      tool_name: 'lookup_host_info',
      tool_input: { hostname: 'web1.example.com' },
      call_id: 'call-1',
    },
    {
      type: 'tool_result',
      timestamp: '2026-07-13T18:27:44Z',
      content: 'RHEL 9.2, OpenSSL 3.0.7, last patched 45 days ago.',
      tool_name: 'lookup_host_info',
      tool_output: 'web1.example.com: RHEL 9.2, OpenSSL 3.0.7, last patched 45 days ago. Environment: production.',
      status: 'success',
      duration_ms: 17,
      call_id: 'call-1',
    },
    {
      type: 'reasoning',
      timestamp: '2026-07-13T18:27:47Z',
      content:
        'OpenSSL 3.0.7 found. 45 days since last patch is concerning. Checking for known CVEs affecting this version.',
      tokens: 39,
      duration_ms: 1202,
    },
    {
      type: 'tool_call',
      timestamp: '2026-07-13T18:27:48Z',
      content: 'Calling check_vulnerabilities',
      tool_name: 'check_vulnerabilities',
      tool_input: { package: 'openssl', version: '3.0.7' },
      call_id: 'call-2',
    },
    {
      type: 'tool_result',
      timestamp: '2026-07-13T18:27:48Z',
      content: 'Found 2 critical CVEs.',
      tool_name: 'check_vulnerabilities',
      tool_output:
        'CVE-2026-1234: RCE via TLS handshake (CVSS 9.1). CVE-2026-5678: DoS via certificate bypass (CVSS 8.4).',
      status: 'success',
      duration_ms: 18,
      call_id: 'call-2',
    },
    {
      type: 'reasoning',
      timestamp: '2026-07-13T18:27:53Z',
      content:
        'Assessment complete. Risk score: 18.2 (2 CVEs × 9.1 CVSS). Recommend immediate patching of all 3 affected hosts.',
      tokens: 189,
      duration_ms: 4583,
    },
  ],
}

const failedToolTrace: AgentTrace = {
  model: 'anthropic/claude-haiku-4.5',
  total_tokens: 50,
  total_duration_ms: 2000,
  steps: [
    {
      type: 'reasoning',
      timestamp: '2026-07-13T18:00:00Z',
      content: 'Let me search the logs for recent errors.',
      tokens: 10,
      duration_ms: 500,
    },
    {
      type: 'tool_call',
      timestamp: '2026-07-13T18:00:01Z',
      content: 'Calling search_logs',
      tool_name: 'search_logs',
      tool_input: { query: 'error', service: 'api-gateway' },
      call_id: 'call-0',
    },
    {
      type: 'tool_result',
      timestamp: '2026-07-13T18:00:02Z',
      content: 'Connection refused',
      tool_name: 'search_logs',
      tool_output: 'Error: Connection refused - Splunk server unreachable',
      status: 'failed',
      duration_ms: 5000,
      call_id: 'call-0',
    },
    {
      type: 'reasoning',
      timestamp: '2026-07-13T18:00:07Z',
      content:
        'The log search failed — Splunk appears to be unreachable. Unable to complete the investigation without log data.',
      tokens: 30,
      duration_ms: 800,
    },
  ],
}

const simpleTrace: AgentTrace = {
  model: 'anthropic/claude-haiku-4.5',
  total_tokens: 20,
  total_duration_ms: 1000,
  steps: [
    {
      type: 'reasoning',
      timestamp: '2026-07-13T18:00:00Z',
      content: 'The sum of 15 and 27 is 42. Hello! How can I help you today?',
      tokens: 20,
      duration_ms: 1000,
    },
  ],
}

export const WithMultipleTools: Story = {
  args: {
    agentTrace: fullTrace,
  },
}

export const WithFailedTool: Story = {
  args: {
    agentTrace: failedToolTrace,
  },
}

export const SimpleReasoning: Story = {
  args: {
    agentTrace: simpleTrace,
  },
}

export const Empty: Story = {
  args: {
    agentTrace: null,
  },
}

export const Loading: Story = {
  args: {
    agentTrace: null,
    isLoading: true,
  },
}
