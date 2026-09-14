import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ValidationError } from '../builderReducer'

import { useValidationEnrichment } from './useValidationEnrichment'

function buildNode(id: string, data: Record<string, unknown> = {}): NodeType {
  return { id, data, position: { x: 0, y: 0 } } as unknown as NodeType
}

describe('useValidationEnrichment', () => {
  it('adds __validationError to nodes matching error node IDs', () => {
    const setNodes = vi.fn()
    const errors: ValidationError[] = [
      { message: 'Node is disconnected', nodeId: 'node-1' },
      { message: 'Missing config', nodeId: 'node-3' },
    ]

    renderHook(() => useValidationEnrichment(errors, true, setNodes))

    expect(setNodes).toHaveBeenCalled()
    const updater = setNodes.mock.calls[0][0] as (nodes: NodeType[]) => NodeType[]
    const input = [buildNode('node-1'), buildNode('node-2'), buildNode('node-3')]
    const result = updater(input)

    expect((result[0].data as Record<string, unknown>).__validationError).toBe(true)
    expect((result[1].data as Record<string, unknown>).__validationError).toBeUndefined()
    expect((result[2].data as Record<string, unknown>).__validationError).toBe(true)
  })

  it('removes __validationError when errors are cleared', () => {
    const setNodes = vi.fn()

    const { rerender } = renderHook(({ errors }) => useValidationEnrichment(errors, true, setNodes), {
      initialProps: { errors: [{ message: 'Error', nodeId: 'node-1' }] as ValidationError[] },
    })

    rerender({ errors: [] })

    const lastCall = setNodes.mock.calls[setNodes.mock.calls.length - 1]
    const updater = lastCall[0] as (nodes: NodeType[]) => NodeType[]
    const input = [buildNode('node-1', { __validationError: true })]
    const result = updater(input)

    expect((result[0].data as Record<string, unknown>).__validationError).toBeUndefined()
  })

  it('leaves nodes untouched when they are not in the error set', () => {
    const setNodes = vi.fn()
    const errors: ValidationError[] = [{ message: 'Error', nodeId: 'node-1' }]

    renderHook(() => useValidationEnrichment(errors, true, setNodes))

    const updater = setNodes.mock.calls[0][0] as (nodes: NodeType[]) => NodeType[]
    const originalNode = buildNode('node-2', { someData: 'value' })
    const result = updater([originalNode])

    expect(result[0]).toBe(originalNode)
  })

  it('does not call setNodes when isInitialized is false', () => {
    const setNodes = vi.fn()
    const errors: ValidationError[] = [{ message: 'Error', nodeId: 'node-1' }]

    renderHook(() => useValidationEnrichment(errors, false, setNodes))

    expect(setNodes).not.toHaveBeenCalled()
  })

  it('returns unchanged array when no mutations are needed', () => {
    const setNodes = vi.fn()
    const errors: ValidationError[] = [{ message: 'Error', nodeId: 'node-1' }]

    renderHook(() => useValidationEnrichment(errors, true, setNodes))

    const updater = setNodes.mock.calls[0][0] as (nodes: NodeType[]) => NodeType[]
    const input = [buildNode('node-1', { __validationError: true })]
    const result = updater(input)

    expect(result).toBe(input)
  })

  it('handles errors with null nodeId gracefully', () => {
    const setNodes = vi.fn()
    const errors: ValidationError[] = [
      { message: 'Global error', nodeId: null },
      { message: 'Node error', nodeId: 'node-1' },
    ]

    renderHook(() => useValidationEnrichment(errors, true, setNodes))

    const updater = setNodes.mock.calls[0][0] as (nodes: NodeType[]) => NodeType[]
    const result = updater([buildNode('node-1'), buildNode('node-2')])

    expect((result[0].data as Record<string, unknown>).__validationError).toBe(true)
    expect((result[1].data as Record<string, unknown>).__validationError).toBeUndefined()
  })

  it('triggers re-enrichment when errors change', () => {
    const setNodes = vi.fn()

    const { rerender } = renderHook(({ errors }) => useValidationEnrichment(errors, true, setNodes), {
      initialProps: { errors: [{ message: 'Error', nodeId: 'node-1' }] as ValidationError[] },
    })

    rerender({ errors: [{ message: 'New error', nodeId: 'node-2' }] })

    expect(setNodes.mock.calls.length).toBeGreaterThanOrEqual(2)
  })
})
