import { describe, expect, it } from 'vitest'

import { normalizeFormPromptNavigationList, sortFormPromptsForNavigation } from './sortFormPromptsForNavigation'

describe('sortFormPromptsForNavigation', () => {
  const workflowDefinition = {
    triggers: [{ id: 'trigger_1', type: 'manual_trigger' }],
    nodes: [
      { id: 'intake_a', type: 'form_prompt' },
      { id: 'intake_b', type: 'form_prompt' },
      { id: 'done', type: 'script' },
    ],
    edges: [
      { from: 'trigger_1', to: 'intake_a' },
      { from: 'intake_a', to: 'intake_b', from_port: 'submitted' },
      { from: 'intake_b', to: 'done', from_port: 'submitted' },
    ],
  }

  it('orders prompts by workflow topology, not API created_at order', () => {
    const apiOrder = [
      { id: 'fp-b', prompt_node_id: 'intake_b', status: 'pending' as const },
      { id: 'fp-a', prompt_node_id: 'intake_a', status: 'submitted' as const },
    ]

    const sorted = sortFormPromptsForNavigation(apiOrder, workflowDefinition, new Map())

    expect(sorted.map((prompt) => prompt.id)).toEqual(['fp-a', 'fp-b'])
  })

  it('returns a single prompt without sorting when only one exists', () => {
    const only = [{ id: 'fp-a', prompt_node_id: 'intake_a', status: 'pending' as const }]
    expect(sortFormPromptsForNavigation(only, workflowDefinition, new Map())).toEqual(only)
  })

  it('defaults index to zero when selected id is missing from list', () => {
    const apiOrder = [{ id: 'fp-a', prompt_node_id: 'intake_a', status: 'pending' as const }]
    const { index } = normalizeFormPromptNavigationList(apiOrder, 'missing', workflowDefinition, new Map())
    expect(index).toBe(0)
  })

  it('returns index zero when no selected prompt id is provided', () => {
    const apiOrder = [
      { id: 'fp-b', prompt_node_id: 'intake_b', status: 'pending' as const },
      { id: 'fp-a', prompt_node_id: 'intake_a', status: 'submitted' as const },
    ]
    const { index } = normalizeFormPromptNavigationList(apiOrder, undefined, workflowDefinition, new Map())
    expect(index).toBe(0)
  })

  it('maps selected prompt to workflow-order index', () => {
    const apiOrder = [
      { id: 'fp-b', prompt_node_id: 'intake_b', status: 'pending' as const },
      { id: 'fp-a', prompt_node_id: 'intake_a', status: 'submitted' as const },
    ]

    const { sorted, index } = normalizeFormPromptNavigationList(apiOrder, 'fp-b', workflowDefinition, new Map())

    expect(sorted.map((prompt) => prompt.id)).toEqual(['fp-a', 'fp-b'])
    expect(index).toBe(1)
  })
})
