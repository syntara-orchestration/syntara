import { describe, expect, it, vi } from 'vitest'

import {
  buildExecutionHistoryRowModel,
  executionDetailHref,
  getClearFiltersHandler,
  resolveVersionStatusForBadge,
  shouldShowSecondaryVersionDatetime,
  workflowVersionHref,
} from './historyRowModel'

describe('buildExecutionHistoryRowModel', () => {
  const base = {
    id: '12345678-abcd-ef00-0000-000000000001',
    created_at: '2024-01-15T10:00:00Z',
    completed_at: '2024-01-15T10:01:00Z',
    status: 'failed',
    mode: 'workflow',
    workflow_id: 'wf-1',
    workflow_version: 3,
    workflow_version_name: 'release',
    workflow_version_created_at: '2024-01-01T00:00:00Z',
    retried_from_execution_id: 'abcdef01-0000-0000-0000-000000000002',
    approval_pending: true,
    execution_metadata: { mode: 'test' as const },
  }

  it('builds a full row model for a retryable test run', () => {
    const model = buildExecutionHistoryRowModel(base, 60_000)

    expect(model.datetimeLabel).toMatch(/Jan 15, 2024/)
    expect(model.showRetryKebab).toBe(true)
    expect(model.elapsedLabel).toMatch(/^Elapsed time:/)
    expect(model.runIdLabel).toBe('Run ID: 12345678')
    expect(model.versionHref).toBe('/workflow-builder/wf-1?version=3')
    expect(model.versionLabel).toBe('release')
    expect(model.retriedFromLabel).toBe('Retried from: abcdef01')
    expect(model.status).toBe('failed')
    expect(model.showTestRun).toBe(true)
    expect(model.approvalPending).toBe(true)
  })

  it('hides optional fields when data is missing', () => {
    const model = buildExecutionHistoryRowModel(
      {
        id: null,
        created_at: null,
        status: 'running',
        mode: 'workflow',
        workflow_version: null,
        workflow_id: null,
        retried_from_execution_id: null,
        approval_pending: null,
        execution_metadata: null,
      },
      undefined
    )

    expect(model.datetimeLabel).toBeNull()
    expect(model.showRetryKebab).toBe(false)
    expect(model.elapsedLabel).toBe('Elapsed time: -')
    expect(model.runIdLabel).toBeNull()
    expect(model.versionHref).toBeNull()
    expect(model.versionLabel).toBeNull()
    expect(model.retriedFromLabel).toBeNull()
    expect(model.showTestRun).toBe(false)
    expect(model.approvalPending).toBeUndefined()
  })

  it('falls back to version created_at when publish name is missing', () => {
    const model = buildExecutionHistoryRowModel(
      {
        ...base,
        workflow_version_name: null,
        workflow_version_created_at: '2024-06-15T14:30:00Z',
      },
      undefined
    )

    expect(model.versionHref).toBe('/workflow-builder/wf-1?version=3')
    expect(model.versionLabel).toBeTruthy()
  })

  it('hides version when workflow_id is missing', () => {
    const model = buildExecutionHistoryRowModel(
      {
        ...base,
        workflow_id: null,
      },
      undefined
    )

    expect(model.versionHref).toBeNull()
    expect(model.versionLabel).toBeNull()
  })

  it('does not mark non-test metadata as a test run', () => {
    const model = buildExecutionHistoryRowModel(
      {
        ...base,
        execution_metadata: { mode: 'normal' },
      },
      undefined
    )

    expect(model.showTestRun).toBe(false)
  })
})

describe('shouldShowSecondaryVersionDatetime', () => {
  it('requires both name and created_at', () => {
    expect(shouldShowSecondaryVersionDatetime('Release', '2024-01-01T00:00:00Z')).toBe(true)
    expect(shouldShowSecondaryVersionDatetime('Release', null)).toBe(false)
    expect(shouldShowSecondaryVersionDatetime(null, '2024-01-01T00:00:00Z')).toBe(false)
    expect(shouldShowSecondaryVersionDatetime(null, null)).toBe(false)
  })
})

describe('resolveVersionStatusForBadge', () => {
  it('returns status only for badge-eligible values', () => {
    expect(resolveVersionStatusForBadge('published')).toBe('published')
    expect(resolveVersionStatusForBadge('previously_published')).toBe('previously_published')
    expect(resolveVersionStatusForBadge('draft')).toBeNull()
    expect(resolveVersionStatusForBadge('nope')).toBeNull()
    expect(resolveVersionStatusForBadge(null)).toBeNull()
    expect(resolveVersionStatusForBadge(undefined)).toBeNull()
  })
})

describe('history row URL helpers', () => {
  it('builds a workflow-builder URL for a given workflow version', () => {
    expect(workflowVersionHref('wf-42', 7)).toBe('/workflow-builder/wf-42?version=7')
  })

  it('builds an executions URL for a given execution id', () => {
    expect(executionDetailHref('exec-abc')).toBe('/executions/exec-abc')
  })
})

describe('getClearFiltersHandler', () => {
  it('returns undefined when onFilterChange is missing', () => {
    expect(getClearFiltersHandler(undefined)).toBeUndefined()
  })

  it('returns a handler that clears filters', () => {
    const onFilterChange = vi.fn()
    const handler = getClearFiltersHandler(onFilterChange)
    expect(handler).toBeTypeOf('function')
    handler?.()
    expect(onFilterChange).toHaveBeenCalledWith([])
  })
})
