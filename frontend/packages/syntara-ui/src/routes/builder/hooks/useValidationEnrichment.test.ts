import { describe, expect, it } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ValidationError } from '../builderReducer'

import { projectValidationEnrichment } from './useValidationEnrichment'

function buildNode(id: string, data: Record<string, unknown> = {}): NodeType {
  return { id, data, position: { x: 0, y: 0 } } as unknown as NodeType
}

describe('projectValidationEnrichment', () => {
  it('adds validation flags to nodes matching workflow error IDs', () => {
    const errors: ValidationError[] = [
      { message: 'Node is disconnected', nodeId: 'node-1' },
      { message: 'Missing config', nodeId: 'node-3' },
    ]
    const result = projectValidationEnrichment(
      [buildNode('node-1'), buildNode('node-2'), buildNode('node-3')],
      errors,
      [],
      true
    )

    expect(result.map((node) => (node.data as Record<string, unknown>).__validationError)).toEqual([
      true,
      undefined,
      true,
    ])
  })

  it('removes validation flags when errors are cleared', () => {
    const result = projectValidationEnrichment(
      [buildNode('node-1', { __validationError: true, label: 'Task' })],
      [],
      [],
      true
    )

    expect(result[0].data).toEqual({ label: 'Task' })
  })

  it('leaves nodes untouched before initialization and ignores errors without node IDs', () => {
    const node = buildNode('node-1')
    const nodes = [node]
    const globalErrors: ValidationError[] = [{ message: 'Global error', nodeId: null }]

    expect(projectValidationEnrichment(nodes, globalErrors, [], false)).toBe(nodes)
    expect(projectValidationEnrichment(nodes, globalErrors, [], true)).toBe(nodes)
  })

  it('preserves the node array when no flags need to change', () => {
    const nodes = [buildNode('node-1', { __validationError: true })]
    const errors: ValidationError[] = [{ message: 'Error', nodeId: 'node-1' }]

    expect(projectValidationEnrichment(nodes, errors, [], true)).toBe(nodes)
  })

  it('maps trigger definition IDs to React Flow display IDs', () => {
    const errors: ValidationError[] = [{ message: 'Invalid trigger', nodeId: 'snow_trigger' }]
    const result = projectValidationEnrichment(
      [buildNode('trigger-0'), buildNode('log_payload')],
      errors,
      [{ id: 'snow_trigger' }],
      true
    )

    expect((result[0].data as Record<string, unknown>).__validationError).toBe(true)
    expect((result[1].data as Record<string, unknown>).__validationError).toBeUndefined()
  })
})
