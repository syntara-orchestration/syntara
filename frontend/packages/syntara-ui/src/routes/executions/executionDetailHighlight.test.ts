import type { Approval, FormsAPI } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import { resolveWaitingNodeHighlightId } from './executionDetailHighlight'

describe('resolveWaitingNodeHighlightId', () => {
  const formPrompt: FormsAPI.components['schemas']['FormPromptSummary'] = {
    id: 'fp-1',
    execution_id: 'exec-1',
    project_id: 'proj-1',
    prompt_node_id: 'collect_input_iter_1',
    name: 'Collect',
    status: 'pending',
    temporal_activity_id: 'act-1',
  }

  const approval: Approval = {
    id: 'ap-1',
    project_id: 'proj-1',
    name: 'Approve',
    status: 'pending',
    execution_id: 'exec-1',
    approval_node_id: 'approve_iter_0',
    created_at: '2026-01-01T00:00:00Z',
    next_step_approved: { id: 'a', name: 'A', type: 'task' },
    workflow_context: { workflow_id: 'w', workflow_name: 'W', inputs: {} },
  }

  it('highlights form prompt canvas id when a form prompt is active', () => {
    expect(resolveWaitingNodeHighlightId(formPrompt, approval)).toBe('collect_input')
  })

  it('highlights approval canvas id when only approval is active', () => {
    expect(resolveWaitingNodeHighlightId(null, approval)).toBe('approve')
  })

  it('returns undefined when neither panel has a selection', () => {
    expect(resolveWaitingNodeHighlightId(null, null)).toBeUndefined()
  })
})
