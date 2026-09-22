import { describe, expect, it } from 'vitest'

import {
  extractNodeKindDenials,
  isNodeKindWriteDeniedError,
  NODE_KIND_WRITE_DENIED_CODE,
  nodeKindWriteDeniedAlert,
} from './nodeKindDenials'

const problemDetails = {
  type: 'https://syntara.dev/problems/forbidden',
  title: 'Forbidden',
  detail: 'Not allowed to add workflow nodes of kind: script, agentic',
  code: NODE_KIND_WRITE_DENIED_CODE,
  retryable: false,
  denied_kinds: [
    { kind: 'script', denied_by: 'no-scripts', reason: 'denied by policy no-scripts' },
    { kind: 'agentic', denied_by: 'no-agents', reason: 'denied by policy no-agents' },
  ],
}

describe('isNodeKindWriteDeniedError', () => {
  it('recognizes the problem-details code', () => {
    expect(isNodeKindWriteDeniedError(problemDetails)).toBe(true)
  })

  it('recognizes the code when the body is nested under cause', () => {
    expect(isNodeKindWriteDeniedError({ cause: problemDetails })).toBe(true)
  })

  it('rejects other error codes and non-objects', () => {
    expect(isNodeKindWriteDeniedError({ code: 'WORKFLOW_VERSION_CONFLICT' })).toBe(false)
    expect(isNodeKindWriteDeniedError(new Error('boom'))).toBe(false)
    expect(isNodeKindWriteDeniedError(undefined)).toBe(false)
  })
})

describe('extractNodeKindDenials', () => {
  it('reads the denied kinds with their policy names', () => {
    expect(extractNodeKindDenials(problemDetails)).toEqual([
      { kind: 'script', denied_by: 'no-scripts', reason: 'denied by policy no-scripts' },
      { kind: 'agentic', denied_by: 'no-agents', reason: 'denied by policy no-agents' },
    ])
  })

  it('unwraps a body nested under cause or data', () => {
    expect(extractNodeKindDenials({ cause: problemDetails })).toHaveLength(2)
    expect(extractNodeKindDenials({ data: problemDetails })).toHaveLength(2)
  })

  it('drops malformed entries and defaults missing string fields', () => {
    const denials = extractNodeKindDenials({
      denied_kinds: [{ kind: 'script' }, { denied_by: 'no-kind' }, null, 'nonsense'],
    })

    expect(denials).toEqual([{ kind: 'script', denied_by: '', reason: '' }])
  })

  it('returns an empty list when there is nothing to read', () => {
    expect(extractNodeKindDenials(undefined)).toEqual([])
    expect(extractNodeKindDenials({ code: NODE_KIND_WRITE_DENIED_CODE })).toEqual([])
  })
})

describe('nodeKindWriteDeniedAlert', () => {
  it('lists every denied kind and the policy that denied it', () => {
    const alert = nodeKindWriteDeniedAlert(problemDetails, 'save')

    expect(alert).toEqual({
      title: 'Cannot save workflow: node kind not allowed',
      description:
        'Your changes were not saved. You are not allowed to add nodes of kind: script (denied by no-scripts), agentic (denied by no-agents).',
    })
  })

  it('uses the given action verb in the title', () => {
    expect(nodeKindWriteDeniedAlert(problemDetails, 'publish')?.title).toBe(
      'Cannot publish workflow: node kind not allowed'
    )
  })

  it('omits the policy name when the backend did not provide one', () => {
    const alert = nodeKindWriteDeniedAlert(
      { code: NODE_KIND_WRITE_DENIED_CODE, denied_kinds: [{ kind: 'mcp_tool' }] },
      'save'
    )

    expect(alert?.description).toContain('kind: mcp_tool.')
  })

  it('falls back to a generic message when the kinds list is missing', () => {
    const alert = nodeKindWriteDeniedAlert({ code: NODE_KIND_WRITE_DENIED_CODE }, 'save')

    expect(alert?.description).toBe(
      'Your changes were not saved. You are not allowed to add one or more of the node kinds in this workflow.'
    )
  })

  it('returns null for unrelated errors so the caller keeps its generic handling', () => {
    expect(nodeKindWriteDeniedAlert({ code: 'WORKFLOW_VERSION_CONFLICT' }, 'save')).toBeNull()
  })
})
