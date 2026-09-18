import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'

import { resolveWorkflowNodeTypeId } from './resolveWorkflowNodeTypeId'

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(),
  },
}))

describe('resolveWorkflowNodeTypeId', () => {
  beforeEach(() => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      currentWorkflow: {
        workflow: {
          activities: [{ id: 'act-1', type: 'script', name: 'Script' }],
        },
        triggers: [
          { id: 'real-trigger-id', type: 'manual_trigger', name: 'Manual' },
          { id: 'webhook-id', type: 'webhook_trigger', name: 'Webhook' },
        ],
      },
    } as never)
  })

  it('resolves activity types by id', () => {
    expect(resolveWorkflowNodeTypeId('act-1')).toBe('script')
  })

  it('resolves trigger types by display id', () => {
    expect(resolveWorkflowNodeTypeId('trigger-0')).toBe('manual_trigger')
    expect(resolveWorkflowNodeTypeId('trigger-1')).toBe('webhook_trigger')
  })

  it('resolves trigger types by real id', () => {
    expect(resolveWorkflowNodeTypeId('real-trigger-id')).toBe('manual_trigger')
  })

  it('returns undefined when workflow is missing', () => {
    vi.mocked(useWorkflowStore.getState).mockReturnValue({ currentWorkflow: null } as never)
    expect(resolveWorkflowNodeTypeId('act-1')).toBeUndefined()
  })
})
