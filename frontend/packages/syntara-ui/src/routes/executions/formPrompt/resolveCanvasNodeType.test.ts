import { FlowNodeType } from '../../../constants'

import { resolveCanvasNodeType } from './resolveCanvasNodeType'

describe('resolveCanvasNodeType', () => {
  it('returns node type from workflow definition nodes', () => {
    const workflowDefinition = {
      nodes: [
        { id: 'collect_input', type: FlowNodeType.FORM_PROMPT },
        { id: 'approve', type: FlowNodeType.APPROVAL },
      ],
    }

    expect(resolveCanvasNodeType('collect_input', workflowDefinition)).toBe(FlowNodeType.FORM_PROMPT)
  })

  it('resolves loop-suffixed activity ids to canvas node type', () => {
    const workflowDefinition = {
      workflow: {
        activities: [{ id: 'collect_input', type: FlowNodeType.FORM_PROMPT }],
      },
    }

    expect(resolveCanvasNodeType('collect_input_iter_1', workflowDefinition)).toBe(FlowNodeType.FORM_PROMPT)
  })

  it('returns undefined when definition is missing', () => {
    expect(resolveCanvasNodeType('collect_input', undefined)).toBeUndefined()
  })

  it('returns undefined when definition node type is not a string', () => {
    const workflowDefinition = {
      nodes: [{ id: 'collect_input', type: 42 }],
    }

    expect(resolveCanvasNodeType('collect_input', workflowDefinition)).toBeUndefined()
  })
})
