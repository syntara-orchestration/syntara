import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import { useWorkflowEngineDefaults } from './useWorkflowEngineDefaults'

const mockGet = vi.fn()
vi.mock('../../../client', () => ({
  settingsFetchClient: { GET: (...args: unknown[]) => mockGet(...args) as unknown },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children)
  }
}

function makeSettingsResponse(overrides: Record<string, unknown> = {}) {
  const defaults: Record<string, unknown> = {
    'workflow_engine.continue_on_failure': false,
    'workflow_engine.script_timeout_seconds': 300,
    'workflow_engine.agentic_timeout_seconds': 300,
    'workflow_engine.aap_timeout_seconds': 3600,
    'workflow_engine.approval_decision_window_seconds': 86400,
    'workflow_engine.converge_wait_duration_seconds': 86400,
    'workflow_engine.http_request_timeout_seconds': 30,
    'workflow_engine.retry_max_retries': 3,
    'workflow_engine.retry_initial_interval': 1,
    'workflow_engine.retry_max_interval': 60,
    'workflow_engine.retry_backoff_coefficient': 2.0,
    'workflow_engine.max_loop_iterations': 1000,
    ...overrides,
  }
  return {
    data: {
      resources: Object.entries(defaults).map(([key, effective_value]) => ({ key, effective_value })),
    },
    error: null,
  }
}

describe('useWorkflowEngineDefaults', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null defaults while loading', () => {
    mockGet.mockReturnValue(new Promise(() => undefined))
    const { result } = renderHook(() => useWorkflowEngineDefaults(), { wrapper: makeWrapper() })
    expect(result.current.defaults).toBeNull()
    expect(result.current.isLoading).toBe(true)
  })

  it('parses all timeout defaults correctly', async () => {
    mockGet.mockResolvedValue(makeSettingsResponse())
    const { result } = renderHook(() => useWorkflowEngineDefaults(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.defaults).not.toBeNull())

    const { timeoutSeconds } = result.current.defaults!
    expect(timeoutSeconds.script).toBe(300)
    expect(timeoutSeconds.agentic).toBe(300)
    expect(timeoutSeconds.aap).toBe(3600)
    expect(timeoutSeconds.approval).toBe(86400)
    expect(timeoutSeconds.http_request).toBe(30)
  })

  it('parses retry defaults correctly', async () => {
    mockGet.mockResolvedValue(makeSettingsResponse())
    const { result } = renderHook(() => useWorkflowEngineDefaults(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.defaults).not.toBeNull())

    const { retry } = result.current.defaults!
    expect(retry.maxRetries).toBe(3)
    expect(retry.initialInterval).toBe(1)
    expect(retry.maxInterval).toBe(60)
    expect(retry.backoffCoefficient).toBe(2.0)
  })

  it('parses continueOnFailure and maxLoopIterations', async () => {
    mockGet.mockResolvedValue(makeSettingsResponse())
    const { result } = renderHook(() => useWorkflowEngineDefaults(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.defaults).not.toBeNull())

    expect(result.current.defaults!.continueOnFailure).toBe(false)
    expect(result.current.defaults!.maxLoopIterations).toBe(1000)
    expect(result.current.defaults!.convergeWaitDuration).toBe(86400)
  })

  it('returns null for missing keys', async () => {
    mockGet.mockResolvedValue({ data: { resources: [] }, error: null })
    const { result } = renderHook(() => useWorkflowEngineDefaults(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.defaults!.timeoutSeconds.script).toBeNull()
    expect(result.current.defaults!.retry.maxRetries).toBeNull()
    expect(result.current.defaults!.continueOnFailure).toBeNull()
  })

  it('throws and returns null defaults on API error', async () => {
    mockGet.mockResolvedValue({ data: null, error: new Error('server error') })
    const { result } = renderHook(() => useWorkflowEngineDefaults(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.defaults).toBeNull()
  })
})
