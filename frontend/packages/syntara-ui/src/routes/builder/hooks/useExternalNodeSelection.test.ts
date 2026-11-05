import { describe, expect, it } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import { projectExternalNodeSelection } from './useExternalNodeSelection'

function makeNode(id: string, selected = false, data: Record<string, unknown> = {}): NodeType {
  return { id, selected, data, position: { x: 0, y: 0 }, type: 'task' } as unknown as NodeType
}

describe('projectExternalNodeSelection', () => {
  it('leaves selection unchanged when selectedActivityId is null or undefined', () => {
    const node = makeNode('step-1', true)
    const nodes = [node]

    expect(projectExternalNodeSelection(nodes, null)).toBe(nodes)
    expect(projectExternalNodeSelection(nodes, undefined)).toBe(nodes)
  })

  it('selects a node by ID and clears other rendered selections', () => {
    const result = projectExternalNodeSelection([makeNode('step-1'), makeNode('step-2', true)], 'step-1')

    expect(result.map((node) => node.selected)).toEqual([true, false])
  })

  it('selects a trigger by definition ID', () => {
    const result = projectExternalNodeSelection(
      [makeNode('trigger-0', false, { definitionId: 'trigger_manual' }), makeNode('step-1')],
      'trigger_manual'
    )

    expect(result.map((node) => node.selected)).toEqual([true, false])
  })

  it('preserves the node and array references when selection is already correct', () => {
    const node = makeNode('step-1', true)
    const nodes = [node]

    expect(projectExternalNodeSelection(nodes, 'step-1')).toBe(nodes)
  })
})
