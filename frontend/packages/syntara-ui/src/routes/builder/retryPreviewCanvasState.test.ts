import { FlowNodeType } from '../../constants'

import { getNotRetriedFailureCount, getRetryPreviewCanvasStates } from './retryPreviewCanvasState'

describe('retry preview canvas state', () => {
  const nodes = [
    { id: 'trigger-0', type: FlowNodeType.TRIGGER, status: 'completed' },
    { id: 'fetch-inventory', type: FlowNodeType.TASK, status: 'completed' },
    { id: 'process-inventory', type: FlowNodeType.TASK, status: 'failed' },
    { id: 'call-api', type: FlowNodeType.TASK, status: 'failed' },
    { id: 'publish-results', type: FlowNodeType.TASK, status: 'skipped' },
    { id: 'fetch-orders', type: FlowNodeType.TASK, status: 'completed' },
  ]
  const edges = [
    { source: 'fetch-inventory', target: 'process-inventory' },
    { source: 'call-api', target: 'publish-results' },
  ]

  it('marks the selected path, retained results, and failed steps outside the selection', () => {
    const states = getRetryPreviewCanvasStates(nodes, edges, ['call-api'])

    expect(states.get('call-api')).toBe('origin')
    expect(states.get('publish-results')).toBe('will-retry')
    expect(states.get('fetch-inventory')).toBe('retained')
    expect(states.get('process-inventory')).toBe('not-retried')
    expect(states.has('trigger-0')).toBe(false)
    expect(states.get('fetch-orders')).toBe('retained')
  })

  it('treats a sanitized replacement as the retry origin for its failed descendant', () => {
    const states = getRetryPreviewCanvasStates(nodes, edges, ['fetch-inventory'])

    expect(states.get('fetch-inventory')).toBe('origin')
    expect(states.get('process-inventory')).toBe('will-retry')
    expect(states.get('call-api')).toBe('not-retried')
  })

  it('counts failed steps that are outside every selected retry path', () => {
    expect(getNotRetriedFailureCount(['process-inventory', 'call-api'], ['call-api'], edges)).toBe(1)
    expect(getNotRetriedFailureCount(['process-inventory', 'call-api'], ['fetch-inventory'], edges)).toBe(1)
  })
})
