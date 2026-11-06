import { EdgeHandleEnum } from '@syntara/contracts'
import type { ReactFlowInstance, Node as FlowNode } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'

import { FlowNodeType } from '../../../constants'

import type { EdgeConnectionParams } from './edgeConnectionHelpers'
import { calculateEdgeConnection, applyEdgeConnection, resetPollingConnectionCounter } from './edgeConnectionHelpers'
import { buildSwitchCasePort } from './switchCaseHelpers'

describe('calculateEdgeConnection', () => {
  const mockReactFlowInstance = {
    getNodes: vi.fn(() => []),
    setEdges: vi.fn(),
    setNodes: vi.fn(),
  } as unknown as ReactFlowInstance

  const mockOnAddNode = vi.fn()

  it('creates basic edge connection from source to target', () => {
    const params: EdgeConnectionParams = {
      sourceId: 'node-1',
      targetId: 'node-2',
      onAddNode: mockOnAddNode,
    }

    const result = calculateEdgeConnection(params, mockReactFlowInstance)

    expect(result.edgesToAdd).toHaveLength(1)
    expect(result.edgesToAdd[0]).toMatchObject({
      source: 'node-1',
      target: 'node-2',
      targetHandle: 'target',
    })
    expect(result.edgeIdsToRemove).toEqual([])
    expect(result.placeholderIdToRemove).toBe('placeholder-node-1')
    expect(result.activityReorderTarget).toBeNull()
  })

  it('creates edge with sourceHandle specified', () => {
    const params: EdgeConnectionParams = {
      sourceId: 'node-1',
      targetId: 'node-2',
      sourceHandle: 'true',
      onAddNode: mockOnAddNode,
    }

    const result = calculateEdgeConnection(params, mockReactFlowInstance)

    expect(result.edgesToAdd[0]).toMatchObject({
      sourceHandle: 'true',
    })
    // Condition handle should create handle-specific placeholder
    expect(result.placeholderIdToRemove).toBe('placeholder-node-1-true')
  })

  it('removes old edge when edgeIdToReplace is provided', () => {
    const params: EdgeConnectionParams = {
      sourceId: 'node-1',
      targetId: 'node-2',
      edgeIdToReplace: 'old-edge-id',
      onAddNode: mockOnAddNode,
    }

    const result = calculateEdgeConnection(params, mockReactFlowInstance)

    expect(result.edgeIdsToRemove).toContain('old-edge-id')
  })

  describe('Edge replacement scenario', () => {
    it('creates second edge when inserting node between two existing nodes', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'node-1',
        targetId: 'new-node',
        edgeIdToReplace: 'old-edge',
        targetNodeId: 'node-2',
        targetHandle: 'target',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      // Should create two edges: source->new and new->target
      expect(result.edgesToAdd).toHaveLength(2)
      expect(result.edgesToAdd[0]).toMatchObject({
        source: 'node-1',
        target: 'new-node',
      })
      expect(result.edgesToAdd[1]).toMatchObject({
        source: 'new-node',
        target: 'node-2',
        sourceHandle: 'source',
        targetHandle: 'target',
      })
      expect(result.activityReorderTarget).toBe('node-2')
    })

    it('uses provided targetHandle in second edge', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'node-1',
        targetId: 'new-node',
        edgeIdToReplace: 'old-edge',
        targetNodeId: 'loop-1',
        targetHandle: 'end',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      expect(result.edgesToAdd[1]).toMatchObject({
        targetHandle: 'end',
      })
    })
  })

  describe('Loop handle scenario', () => {
    it('creates loop-back edge when sourceHandle is "loop"', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'loop-1',
        targetId: 'task-1',
        sourceHandle: 'loop',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      // Should create two edges: loop->task and task->loop (back)
      expect(result.edgesToAdd).toHaveLength(2)
      expect(result.edgesToAdd[1]).toMatchObject({
        source: 'task-1',
        target: 'loop-1',
        sourceHandle: 'source',
        targetHandle: 'end',
      })
    })

    it('does not create loop-back edge when edgeIdToReplace is set', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'loop-1',
        targetId: 'task-1',
        sourceHandle: 'loop',
        edgeIdToReplace: 'some-edge',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      // Should only create the primary edge, not the loop-back
      expect(result.edgesToAdd).toHaveLength(1)
    })
  })

  describe('Placeholder ID calculation', () => {
    it('uses handle-specific placeholder for condition handles', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'cond-1',
        targetId: 'task-1',
        sourceHandle: 'false',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      expect(result.placeholderIdToRemove).toBe('placeholder-cond-1-false')
    })

    it('uses handle-specific placeholder for loop handles', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'loop-1',
        targetId: 'task-1',
        sourceHandle: 'done',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      expect(result.placeholderIdToRemove).toBe('placeholder-loop-1-done')
    })

    it('uses handle-specific placeholder for switch case handles', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'switch-1',
        targetId: 'task-1',
        sourceHandle: buildSwitchCasePort(0),
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      expect(result.placeholderIdToRemove).toBe(`placeholder-switch-1-${buildSwitchCasePort(0)}`)
    })

    it('uses handle-specific placeholder for switch default handle', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'switch-1',
        targetId: 'task-1',
        sourceHandle: EdgeHandleEnum.DEFAULT,
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      expect(result.placeholderIdToRemove).toBe(`placeholder-switch-1-${EdgeHandleEnum.DEFAULT}`)
    })

    it('uses simple placeholder for other handles', () => {
      const params: EdgeConnectionParams = {
        sourceId: 'task-1',
        targetId: 'task-2',
        sourceHandle: 'source',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockReactFlowInstance)

      expect(result.placeholderIdToRemove).toBe('placeholder-task-1')
    })
  })

  describe('Button edge class removal logic', () => {
    it('keeps button edge class when condition node has other placeholders', () => {
      const mockInstanceWithPlaceholders = {
        getNodes: vi.fn(() => [
          { id: 'cond-1', type: FlowNodeType.CONDITION },
          { id: 'placeholder-cond-1-false' }, // Other branch still has placeholder
        ]),
        setEdges: vi.fn(),
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      const params: EdgeConnectionParams = {
        sourceId: 'cond-1',
        targetId: 'task-1',
        sourceHandle: 'true',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockInstanceWithPlaceholders)

      expect(result.shouldRemoveButtonEdgeClass).toBe(false)
    })

    it('keeps button edge class when loop node has other placeholders', () => {
      const mockInstanceWithPlaceholders = {
        getNodes: vi.fn(() => [
          { id: 'loop-1', type: FlowNodeType.LOOP },
          { id: 'placeholder-loop-1-loop' }, // Loop branch still has placeholder
        ]),
        setEdges: vi.fn(),
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      const params: EdgeConnectionParams = {
        sourceId: 'loop-1',
        targetId: 'task-1',
        sourceHandle: 'done',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockInstanceWithPlaceholders)

      expect(result.shouldRemoveButtonEdgeClass).toBe(false)
    })

    it('keeps button edge class when switch node has other placeholders', () => {
      const mockInstanceWithPlaceholders = {
        getNodes: vi.fn(() => [
          { id: 'switch-1', type: FlowNodeType.SWITCH },
          { id: `placeholder-switch-1-${EdgeHandleEnum.DEFAULT}` },
        ]),
        setEdges: vi.fn(),
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      const params: EdgeConnectionParams = {
        sourceId: 'switch-1',
        targetId: 'task-1',
        sourceHandle: buildSwitchCasePort(0),
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockInstanceWithPlaceholders)

      expect(result.shouldRemoveButtonEdgeClass).toBe(false)
    })

    it('removes button edge class when no placeholders remain', () => {
      const mockInstanceNoPlaceholders = {
        getNodes: vi.fn(() => [
          { id: 'node-1', type: 'task' },
          // No placeholders
        ]),
        setEdges: vi.fn(),
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      const params: EdgeConnectionParams = {
        sourceId: 'node-1',
        targetId: 'node-2',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockInstanceNoPlaceholders)

      expect(result.shouldRemoveButtonEdgeClass).toBe(true)
    })

    it('returns false when source node not found', () => {
      const mockInstanceNoSource = {
        getNodes: vi.fn(() => [
          // Source node doesn't exist
        ]),
        setEdges: vi.fn(),
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      const params: EdgeConnectionParams = {
        sourceId: 'missing-node',
        targetId: 'node-2',
        onAddNode: mockOnAddNode,
      }

      const result = calculateEdgeConnection(params, mockInstanceNoSource)

      expect(result.shouldRemoveButtonEdgeClass).toBe(false)
    })
  })
})

describe('applyEdgeConnection', () => {
  it('waits for target node to be measured before applying changes', () => {
    vi.useFakeTimers()

    const unmeasuredNode: Partial<FlowNode> = {
      id: 'target',
      measured: undefined,
      position: { x: 0, y: 0 },
      data: {},
    }
    const setEdges = vi.fn()
    const setNodes = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [unmeasuredNode as FlowNode]),
      setEdges,
      setNodes,
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'source',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [],
      edgeIdsToRemove: [],
      placeholderIdToRemove: 'placeholder-source',
      shouldRemoveButtonEdgeClass: true,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
    })

    // Should not apply changes yet
    expect(setEdges).not.toHaveBeenCalled()

    // Mark node as measured
    unmeasuredNode.measured = { width: 100, height: 50 }
    mockInstance.getNodes = vi.fn(() => [unmeasuredNode as FlowNode])

    // Fast-forward timer
    vi.advanceTimersByTime(50)

    // Now should apply changes
    expect(setEdges).toHaveBeenCalled()

    vi.useRealTimers()
  })

  it('calls onComplete callback after applying changes', () => {
    const measuredNode: Partial<FlowNode> = {
      id: 'target',
      measured: { width: 100, height: 50 },
      position: { x: 0, y: 0 },
      data: {},
    }
    const onComplete = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [measuredNode as FlowNode]),
      setEdges: vi.fn(),
      setNodes: vi.fn(),
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'source',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [],
      edgeIdsToRemove: [],
      placeholderIdToRemove: null,
      shouldRemoveButtonEdgeClass: false,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
      onComplete: onComplete,
    })

    expect(onComplete).toHaveBeenCalled()
  })

  it('stops retrying after 40 attempts', () => {
    vi.useFakeTimers()

    const unmeasuredNode = { id: 'target', measured: false }
    const setEdges = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [unmeasuredNode]),
      setEdges,
      setNodes: vi.fn(),
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'source',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [],
      edgeIdsToRemove: [],
      placeholderIdToRemove: null,
      shouldRemoveButtonEdgeClass: false,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
    })

    // Fast-forward through all retry attempts
    vi.advanceTimersByTime(50 * 40)

    // Should have given up
    expect(setEdges).not.toHaveBeenCalled()

    vi.useRealTimers()
  })

  it('removes button edges and old edges when adding new edges', () => {
    const measuredNode = { id: 'target', measured: true }
    const newEdge = { id: 'new-edge', source: 'source', target: 'target' }

    const setEdges = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [measuredNode]),
      setEdges,
      setNodes: vi.fn(),
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'source',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [newEdge],
      edgeIdsToRemove: ['old-edge'],
      placeholderIdToRemove: null,
      shouldRemoveButtonEdgeClass: false,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
    })

    expect(setEdges).toHaveBeenCalled()

    // Verify callback behavior (filtering old edges and adding new ones)
    type EdgeWithId = {
      id: string
    }
    const callback = setEdges.mock.calls[0][0] as (edges: EdgeWithId[]) => EdgeWithId[]
    const existingEdges: EdgeWithId[] = [{ id: 'old-edge' }, { id: 'other-edge' }]
    const resultEdges = callback(existingEdges)

    // Should filter out old-edge (in edgeIdsToRemove)
    expect(resultEdges.find((e) => e.id === 'old-edge')).toBeUndefined()
    // Should keep other edges
    expect(resultEdges.find((e) => e.id === 'other-edge')).toBeDefined()
    // Should include new edge
    expect(resultEdges.find((e) => e.id === 'new-edge')).toBeDefined()
  })

  it('removes placeholder node and updates button edge class when source is regular node', () => {
    const measuredNode: Partial<FlowNode> = {
      id: 'target',
      measured: { width: 100, height: 50 },
      position: { x: 0, y: 0 },
      data: {},
    }
    const sourceNode: Partial<FlowNode> = {
      id: 'source',
      type: 'task',
      className: 'has-button-edge',
      position: { x: 0, y: 0 },
      data: {},
    }
    const placeholderNode: Partial<FlowNode> = { id: 'placeholder-source', position: { x: 0, y: 0 }, data: {} }

    const setNodes = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [measuredNode, sourceNode, placeholderNode] as FlowNode[]),
      setEdges: vi.fn(),
      setNodes,
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'source',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [],
      edgeIdsToRemove: [],
      placeholderIdToRemove: 'placeholder-source',
      shouldRemoveButtonEdgeClass: true,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
    })

    expect(setNodes).toHaveBeenCalled()

    // Verify the callback modifies nodes correctly
    const callback = setNodes.mock.calls[0][0] as (nodes: FlowNode[]) => FlowNode[]
    const inputNodes = [sourceNode, placeholderNode] as FlowNode[]
    const outputNodes = callback(inputNodes)

    // Should remove placeholder
    expect(outputNodes).toHaveLength(1)
    expect(outputNodes.find((n) => n.id === 'placeholder-source')).toBeUndefined()
    // Should remove button edge class from source node
    expect(outputNodes[0].className).not.toContain('has-button-edge')
  })

  it('keeps button edge class for condition node with remaining placeholders', () => {
    const measuredNode: Partial<FlowNode> = {
      id: 'target',
      measured: { width: 100, height: 50 },
      position: { x: 0, y: 0 },
      data: {},
    }
    const sourceNode: Partial<FlowNode> = {
      id: 'cond-1',
      type: FlowNodeType.CONDITION,
      className: 'has-button-edge',
      position: { x: 0, y: 0 },
      data: {},
    }
    const placeholderTrue: Partial<FlowNode> = { id: 'placeholder-cond-1-true', position: { x: 0, y: 0 }, data: {} }
    const placeholderFalse: Partial<FlowNode> = {
      id: 'placeholder-cond-1-false',
      position: { x: 0, y: 0 },
      data: {},
    }

    const setNodes = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [measuredNode, sourceNode, placeholderTrue, placeholderFalse] as FlowNode[]),
      setEdges: vi.fn(),
      setNodes,
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'cond-1',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [],
      edgeIdsToRemove: [],
      placeholderIdToRemove: 'placeholder-cond-1-true',
      shouldRemoveButtonEdgeClass: false,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
    })

    expect(setNodes).toHaveBeenCalled()

    // Verify the callback keeps button edge class
    const callback = setNodes.mock.calls[0][0] as (nodes: FlowNode[]) => FlowNode[]
    const inputNodes = [sourceNode, placeholderFalse] as FlowNode[]
    const outputNodes = callback(inputNodes)

    // Should remove placeholder-cond-1-true (already gone from input)
    // Should keep button edge class because placeholder-cond-1-false still exists
    const updatedSource = outputNodes.find((n) => n.id === 'cond-1')
    expect(updatedSource?.className).toContain('has-button-edge')
  })

  it('keeps button edge class for loop node with remaining placeholders', () => {
    const measuredNode: Partial<FlowNode> = {
      id: 'target',
      measured: { width: 100, height: 50 },
      position: { x: 0, y: 0 },
      data: {},
    }
    const sourceNode: Partial<FlowNode> = {
      id: 'loop-1',
      type: FlowNodeType.LOOP,
      className: 'has-button-edge',
      position: { x: 0, y: 0 },
      data: {},
    }
    const placeholderDone: Partial<FlowNode> = { id: 'placeholder-loop-1-done', position: { x: 0, y: 0 }, data: {} }
    const placeholderLoop: Partial<FlowNode> = { id: 'placeholder-loop-1-loop', position: { x: 0, y: 0 }, data: {} }

    const setNodes = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [measuredNode, sourceNode, placeholderDone, placeholderLoop] as FlowNode[]),
      setEdges: vi.fn(),
      setNodes,
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'loop-1',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [],
      edgeIdsToRemove: [],
      placeholderIdToRemove: 'placeholder-loop-1-done',
      shouldRemoveButtonEdgeClass: false,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
    })

    expect(setNodes).toHaveBeenCalled()

    // Verify the callback keeps button edge class
    const callback = setNodes.mock.calls[0][0] as (nodes: FlowNode[]) => FlowNode[]
    const inputNodes = [sourceNode, placeholderLoop] as FlowNode[]
    const outputNodes = callback(inputNodes)

    // Should keep button edge class because placeholder-loop-1-loop still exists
    const updatedSource = outputNodes.find((n) => n.id === 'loop-1')
    expect(updatedSource?.className).toContain('has-button-edge')
  })

  it('handles missing source node in setNodes callback', () => {
    const measuredNode: Partial<FlowNode> = {
      id: 'target',
      measured: { width: 100, height: 50 },
      position: { x: 0, y: 0 },
      data: {},
    }
    const placeholderNode: Partial<FlowNode> = { id: 'placeholder-source', position: { x: 0, y: 0 }, data: {} }

    const setNodes = vi.fn()

    const mockInstance = {
      getNodes: vi.fn(() => [measuredNode, placeholderNode] as FlowNode[]),
      setEdges: vi.fn(),
      setNodes,
    } as unknown as ReactFlowInstance

    const params: EdgeConnectionParams = {
      sourceId: 'source',
      targetId: 'target',
      onAddNode: vi.fn(),
    }

    const result = {
      edgesToAdd: [],
      edgeIdsToRemove: [],
      placeholderIdToRemove: 'placeholder-source',
      shouldRemoveButtonEdgeClass: true,
      activityReorderTarget: null,
    }

    applyEdgeConnection({
      result,
      params,
      targetId: 'target',
      reactFlowInstance: mockInstance,
    })

    expect(setNodes).toHaveBeenCalled()

    // Verify the callback handles missing source node
    const callback = setNodes.mock.calls[0][0] as (nodes: FlowNode[]) => FlowNode[]
    const inputNodes = [placeholderNode] as FlowNode[]
    const outputNodes = callback(inputNodes)

    // Should just remove placeholder, no source node to update
    expect(outputNodes).toHaveLength(0)
  })

  describe('concurrency limit (security)', () => {
    beforeEach(() => {
      resetPollingConnectionCounter()
    })

    it('rejects new connections when max concurrent limit reached', () => {
      vi.useFakeTimers()

      const unmeasuredNode = { id: 'target', measured: false }
      const setEdges = vi.fn()
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

      const mockInstance = {
        getNodes: vi.fn(() => [unmeasuredNode]),
        setEdges,
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      const params: EdgeConnectionParams = {
        sourceId: 'source',
        targetId: 'target',
        onAddNode: vi.fn(),
      }

      const result = {
        edgesToAdd: [],
        edgeIdsToRemove: [],
        placeholderIdToRemove: null,
        shouldRemoveButtonEdgeClass: false,
        activityReorderTarget: null,
      }

      // Start 5 connections (max limit)
      for (let i = 0; i < 5; i++) {
        applyEdgeConnection({
          result,
          params,
          targetId: `target-${i}`,
          reactFlowInstance: mockInstance,
        })
      }

      // 6th connection should be rejected
      applyEdgeConnection({
        result,
        params,
        targetId: 'target-6',
        reactFlowInstance: mockInstance,
      })

      expect(consoleWarnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Edge connection rejected: max concurrent limit (5) reached')
      )

      vi.useRealTimers()
      consoleWarnSpy.mockRestore()
    })

    it('decrements counter on successful connection', () => {
      const setEdges = vi.fn()

      const params: EdgeConnectionParams = {
        sourceId: 'source',
        targetId: 'target',
        onAddNode: vi.fn(),
      }

      const result = {
        edgesToAdd: [],
        edgeIdsToRemove: [],
        placeholderIdToRemove: null,
        shouldRemoveButtonEdgeClass: false,
        activityReorderTarget: null,
      }

      // Apply 5 connections with measured nodes (should all succeed immediately and decrement)
      for (let i = 0; i < 5; i++) {
        const measuredNode = { id: `target-${i}`, measured: { width: 100, height: 50 } }
        const mockInstance = {
          getNodes: vi.fn(() => [measuredNode]),
          setEdges,
          setNodes: vi.fn(),
        } as unknown as ReactFlowInstance

        applyEdgeConnection({
          result,
          params,
          targetId: `target-${i}`,
          reactFlowInstance: mockInstance,
        })
      }

      // All 5 should have succeeded (counter incremented then immediately decremented)
      expect(setEdges).toHaveBeenCalledTimes(5)

      // After all completed, counter should be 0, so one more should work
      const measuredNode = { id: 'target-6', measured: { width: 100, height: 50 } }
      const mockInstance = {
        getNodes: vi.fn(() => [measuredNode]),
        setEdges,
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      applyEdgeConnection({
        result,
        params,
        targetId: 'target-6',
        reactFlowInstance: mockInstance,
      })
      expect(setEdges).toHaveBeenCalledTimes(6)
    })

    it('decrements counter on timeout', () => {
      vi.useFakeTimers()

      const unmeasuredNode = { id: 'target', measured: false }
      const setEdges = vi.fn()

      const mockInstance = {
        getNodes: vi.fn(() => [unmeasuredNode]),
        setEdges,
        setNodes: vi.fn(),
      } as unknown as ReactFlowInstance

      const params: EdgeConnectionParams = {
        sourceId: 'source',
        targetId: 'target',
        onAddNode: vi.fn(),
      }

      const result = {
        edgesToAdd: [],
        edgeIdsToRemove: [],
        placeholderIdToRemove: null,
        shouldRemoveButtonEdgeClass: false,
        activityReorderTarget: null,
      }

      // Start connection that will timeout
      applyEdgeConnection({
        result,
        params,
        targetId: 'target',
        reactFlowInstance: mockInstance,
      })

      // Fast-forward through all retry attempts (timeout)
      vi.advanceTimersByTime(50 * 40)

      // Counter should be decremented, allowing new connections
      const measuredNode = { id: 'target2', measured: { width: 100, height: 50 }, position: { x: 0, y: 0 }, data: {} }
      mockInstance.getNodes = vi.fn(() => [measuredNode as FlowNode])

      // This should succeed (counter was decremented after timeout)
      applyEdgeConnection({
        result,
        params,
        targetId: 'target2',
        reactFlowInstance: mockInstance,
      })
      expect(setEdges).toHaveBeenCalled()

      vi.useRealTimers()
    })
  })
})
