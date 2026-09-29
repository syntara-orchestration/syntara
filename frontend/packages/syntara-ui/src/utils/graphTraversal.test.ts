import type { Edge, Node } from '@xyflow/react'
import { describe, it, expect } from 'vitest'

import { getAncestorNodes } from './graphTraversal'

describe('getAncestorNodes', () => {
  it('returns ancestors in a linear chain', () => {
    // Arrange
    const edges = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'c' },
    ] as Edge[]

    const nodes = [
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
      { id: 'c', data: { name: 'Node C' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('c', edges, nodes)

    // Assert
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Node A' }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'b', name: 'Node B' }))
  })

  it('returns ancestors in a diamond/join pattern', () => {
    // Arrange
    const edges = [
      { id: 'e1', source: 'a', target: 'c' },
      { id: 'e2', source: 'b', target: 'c' },
    ] as Edge[]

    const nodes = [
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
      { id: 'c', data: { name: 'Node C' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('c', edges, nodes)

    // Assert
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Node A' }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'b', name: 'Node B' }))
  })

  it('returns empty array for root node with no predecessors', () => {
    // Arrange
    const edges = [{ id: 'e1', source: 'a', target: 'b' }] as Edge[]

    const nodes = [
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('a', edges, nodes)

    // Assert
    expect(result).toHaveLength(0)
  })

  it('handles cycles without infinite loop', () => {
    // Arrange
    const edges = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'a' }, // Creates a cycle
    ] as Edge[]

    const nodes = [
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('b', edges, nodes)

    // Assert
    // In a cycle A→B→A, starting from B (target) will find A (direct ancestor)
    // B itself is excluded because it's the target node (seeded in visited set)
    expect(result).toHaveLength(1)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Node A' }))
  })

  it('uses node name when available, falls back to ID', () => {
    // Arrange
    const edges = [
      { id: 'e1', source: 'a', target: 'c' },
      { id: 'e2', source: 'b', target: 'c' },
    ] as Edge[]

    const nodes = [
      { id: 'a', data: { name: 'Custom Name A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: {}, position: { x: 0, y: 0 } }, // No name property
      { id: 'c', data: { name: 'Node C' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('c', edges, nodes)

    // Assert
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Custom Name A' }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'b', name: 'b' })) // Falls back to ID
  })

  it('handles missing node data gracefully', () => {
    // Arrange
    const edges = [{ id: 'e1', source: 'a', target: 'b' }] as Edge[]

    const nodes = [
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act - reference a node that doesn't exist in nodes array
    const result = getAncestorNodes('b', edges, [nodes[1]])

    // Assert
    expect(result).toHaveLength(1)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'a' })) // Falls back to ID
  })

  it('excludes trigger nodes from ancestors', () => {
    // Arrange — trigger-0 → a → b
    const edges = [
      { id: 'e1', source: 'trigger-0', target: 'a' },
      { id: 'e2', source: 'a', target: 'b' },
    ] as Edge[]

    const nodes = [
      { id: 'trigger-0', data: { name: 'Manual trigger' }, position: { x: 0, y: 0 } },
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('b', edges, nodes)

    // Assert — trigger-0 is traversed but not included in output
    expect(result).toHaveLength(1)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Node A' }))
  })

  it('includes connected trigger ancestors when includeTriggers is true', () => {
    // Arrange — trigger-0 → a → b
    const edges = [
      { id: 'e1', source: 'trigger-0', target: 'a' },
      { id: 'e2', source: 'a', target: 'b' },
    ] as Edge[]

    const nodes = [
      { id: 'trigger-0', data: { name: 'Manual trigger' }, position: { x: 0, y: 0 } },
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('b', edges, nodes, { includeTriggers: true })

    // Assert — trigger-0 is included with isTrigger flag
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Node A' }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'trigger-0', name: 'Manual trigger', isTrigger: true }))
  })

  it('only includes connected triggers, not all triggers in the workflow', () => {
    // Arrange — trigger-0 → a → target, trigger-1 → b (disconnected from target)
    const edges = [
      { id: 'e1', source: 'trigger-0', target: 'a' },
      { id: 'e2', source: 'a', target: 'target' },
      { id: 'e3', source: 'trigger-1', target: 'b' },
    ] as Edge[]

    const nodes = [
      { id: 'trigger-0', data: { name: 'Manual trigger' }, position: { x: 0, y: 0 } },
      { id: 'trigger-1', data: { name: 'Webhook trigger' }, position: { x: 0, y: 0 } },
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
      { id: 'target', data: { name: 'Target' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('target', edges, nodes, { includeTriggers: true })

    // Assert — only trigger-0 is an ancestor of target, not trigger-1
    expect(result).toHaveLength(2)
    expect(result).toContainEqual(expect.objectContaining({ id: 'trigger-0', name: 'Manual trigger', isTrigger: true }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Node A' }))
    expect(result).not.toContainEqual(expect.objectContaining({ id: 'trigger-1' }))
  })

  it('does not set isTrigger on non-trigger ancestors when includeTriggers is true', () => {
    // Arrange — trigger-0 → a → b
    const edges = [
      { id: 'e1', source: 'trigger-0', target: 'a' },
      { id: 'e2', source: 'a', target: 'b' },
    ] as Edge[]

    const nodes = [
      { id: 'trigger-0', data: { name: 'Manual trigger' }, position: { x: 0, y: 0 } },
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('b', edges, nodes, { includeTriggers: true })

    // Assert — non-trigger ancestors should not have isTrigger
    const nodeA = result.find((n) => n.id === 'a')
    expect(nodeA).toBeDefined()
    expect(nodeA).not.toHaveProperty('isTrigger')
  })

  it('handles complex graph with multiple levels', () => {
    // Arrange
    const edges = [
      { id: 'e1', source: 'a', target: 'b' },
      { id: 'e2', source: 'b', target: 'c' },
      { id: 'e3', source: 'c', target: 'd' },
      { id: 'e4', source: 'x', target: 'b' }, // Another path to b
    ] as Edge[]

    const nodes = [
      { id: 'a', data: { name: 'Node A' }, position: { x: 0, y: 0 } },
      { id: 'b', data: { name: 'Node B' }, position: { x: 0, y: 0 } },
      { id: 'c', data: { name: 'Node C' }, position: { x: 0, y: 0 } },
      { id: 'd', data: { name: 'Node D' }, position: { x: 0, y: 0 } },
      { id: 'x', data: { name: 'Node X' }, position: { x: 0, y: 0 } },
    ] as Node[]

    // Act
    const result = getAncestorNodes('d', edges, nodes)

    // Assert
    expect(result).toHaveLength(4)
    expect(result).toContainEqual(expect.objectContaining({ id: 'a', name: 'Node A' }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'b', name: 'Node B' }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'c', name: 'Node C' }))
    expect(result).toContainEqual(expect.objectContaining({ id: 'x', name: 'Node X' }))
  })

  // Control-Flow Traversal Tests
  describe('Control-Flow Traversal', () => {
    // Helper functions for creating test data structures
    function createMockNode(id: string, name: string, position = { x: 0, y: 0 }) {
      return {
        id,
        data: { name },
        position,
      } as Node
    }

    function createMockEdge(id: string, source: string, target: string, sourceHandle?: string) {
      return {
        id,
        source,
        target,
        ...(sourceHandle && { sourceHandle }),
      } as Edge
    }

    describe('Condition Branch Discovery', () => {
      it('discovers predecessors through both condition branches', () => {
        // Arrange - Diamond pattern: start → condition → [true: nodeA, false: nodeB] → converge → target
        const edges = [
          createMockEdge('e1', 'start', 'condition'),
          createMockEdge('e2', 'condition', 'nodeA', 'true'),
          createMockEdge('e3', 'condition', 'nodeB', 'false'),
          createMockEdge('e4', 'nodeA', 'converge'),
          createMockEdge('e5', 'nodeB', 'converge'),
          createMockEdge('e6', 'converge', 'target'),
        ]

        const nodes = [
          createMockNode('start', 'Start Task'),
          createMockNode('condition', 'Check Environment'),
          createMockNode('nodeA', 'Dev Path'),
          createMockNode('nodeB', 'Prod Path'),
          createMockNode('converge', 'Merge Results'),
          createMockNode('target', 'Final Step'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(5)
        expect(result).toContainEqual(expect.objectContaining({ id: 'start', name: 'Start Task' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'condition', name: 'Check Environment' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'nodeA', name: 'Dev Path' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'nodeB', name: 'Prod Path' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'converge', name: 'Merge Results' }))
      })

      it('handles condition with only one connected branch', () => {
        // Arrange - Test case where condition has true branch but false branch is unconnected
        const edges = [
          createMockEdge('e1', 'start', 'condition'),
          createMockEdge('e2', 'condition', 'nodeA', 'true'),
          // No false branch connection
          createMockEdge('e3', 'nodeA', 'target'),
        ]

        const nodes = [
          createMockNode('start', 'Start Task'),
          createMockNode('condition', 'Check Environment'),
          createMockNode('nodeA', 'True Path'),
          createMockNode('target', 'Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(3)
        expect(result).toContainEqual(expect.objectContaining({ id: 'start', name: 'Start Task' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'condition', name: 'Check Environment' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'nodeA', name: 'True Path' }))
      })

      it('handles condition branches with different handle names', () => {
        // Arrange - Condition with custom handle names
        const edges = [
          createMockEdge('e1', 'setup', 'condition'),
          createMockEdge('e2', 'condition', 'success_path', 'yes'),
          createMockEdge('e3', 'condition', 'error_path', 'no'),
          createMockEdge('e4', 'success_path', 'target'),
          createMockEdge('e5', 'error_path', 'target'),
        ]

        const nodes = [
          createMockNode('setup', 'Setup'),
          createMockNode('condition', 'Validation Check'),
          createMockNode('success_path', 'Success Handler'),
          createMockNode('error_path', 'Error Handler'),
          createMockNode('target', 'Cleanup'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(4)
        expect(result).toContainEqual(expect.objectContaining({ id: 'setup', name: 'Setup' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'condition', name: 'Validation Check' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'success_path', name: 'Success Handler' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'error_path', name: 'Error Handler' }))
      })
    })

    describe('Converge Node Discovery', () => {
      it('discovers all inputs to converge node', () => {
        // Arrange - Multiple parallel paths converging
        const edges = [
          createMockEdge('e1', 'pathA_start', 'pathA_end'),
          createMockEdge('e2', 'pathB_start', 'pathB_end'),
          createMockEdge('e3', 'pathC_start', 'pathC_end'),
          createMockEdge('e4', 'pathA_end', 'converge'),
          createMockEdge('e5', 'pathB_end', 'converge'),
          createMockEdge('e6', 'pathC_end', 'converge'),
          createMockEdge('e7', 'converge', 'target'),
        ]

        const nodes = [
          createMockNode('pathA_start', 'Path A Start'),
          createMockNode('pathA_end', 'Path A End'),
          createMockNode('pathB_start', 'Path B Start'),
          createMockNode('pathB_end', 'Path B End'),
          createMockNode('pathC_start', 'Path C Start'),
          createMockNode('pathC_end', 'Path C End'),
          createMockNode('converge', 'Converge Point'),
          createMockNode('target', 'Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(7) // All nodes except target
        expect(result.map((node) => node.id)).toEqual(
          expect.arrayContaining([
            'pathA_start',
            'pathA_end',
            'pathB_start',
            'pathB_end',
            'pathC_start',
            'pathC_end',
            'converge',
          ])
        )
      })

      it('handles converge node as intermediate step', () => {
        // Arrange - Converge node that itself feeds into another converge
        const edges = [
          createMockEdge('e1', 'input1', 'converge1'),
          createMockEdge('e2', 'input2', 'converge1'),
          createMockEdge('e3', 'input3', 'converge2'),
          createMockEdge('e4', 'converge1', 'converge2'),
          createMockEdge('e5', 'converge2', 'target'),
        ]

        const nodes = [
          createMockNode('input1', 'Input 1'),
          createMockNode('input2', 'Input 2'),
          createMockNode('input3', 'Input 3'),
          createMockNode('converge1', 'First Merge'),
          createMockNode('converge2', 'Final Merge'),
          createMockNode('target', 'Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(5)
        expect(result.map((node) => node.id)).toEqual(
          expect.arrayContaining(['input1', 'input2', 'input3', 'converge1', 'converge2'])
        )
      })
    })

    describe('Loop Traversal', () => {
      it('handles loop cycles without infinite recursion', () => {
        // Arrange - Loop structure: start → loop → [done: target, loop: body] → loop
        const edges = [
          createMockEdge('e1', 'start', 'loop'),
          createMockEdge('e2', 'loop', 'target', 'done'),
          createMockEdge('e3', 'loop', 'loopBody', 'loop'),
          createMockEdge('e4', 'loopBody', 'loop'), // Creates cycle
        ]

        const nodes = [
          createMockNode('start', 'Start'),
          createMockNode('loop', 'Loop Control'),
          createMockNode('loopBody', 'Loop Body'),
          createMockNode('target', 'After Loop'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert - Should include all relevant nodes without infinite loop
        expect(result).toHaveLength(3)
        expect(result).toContainEqual(expect.objectContaining({ id: 'start', name: 'Start' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'loop', name: 'Loop Control' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'loopBody', name: 'Loop Body' }))
      })

      it('discovers predecessors from inside loop body', () => {
        // Arrange - Test when target is inside loop body
        const edges = [
          createMockEdge('e1', 'setup', 'loop'),
          createMockEdge('e2', 'loop', 'step1', 'loop'),
          createMockEdge('e3', 'step1', 'step2'),
          createMockEdge('e4', 'step2', 'target'),
          createMockEdge('e5', 'target', 'loop'), // Back to loop
        ]

        const nodes = [
          createMockNode('setup', 'Setup'),
          createMockNode('loop', 'Loop'),
          createMockNode('step1', 'Step 1'),
          createMockNode('step2', 'Step 2'),
          createMockNode('target', 'Target Step'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(4)
        expect(result).toContainEqual(expect.objectContaining({ id: 'setup', name: 'Setup' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'loop', name: 'Loop' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'step1', name: 'Step 1' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'step2', name: 'Step 2' }))
      })

      it('handles multiple loop exit paths', () => {
        // Arrange - Loop with multiple done conditions
        const edges = [
          createMockEdge('e1', 'start', 'loop'),
          createMockEdge('e2', 'loop', 'success_exit', 'done'),
          createMockEdge('e3', 'loop', 'error_exit', 'error'),
          createMockEdge('e4', 'loop', 'loop_body', 'continue'),
          createMockEdge('e5', 'loop_body', 'loop'),
          createMockEdge('e6', 'success_exit', 'target'),
          createMockEdge('e7', 'error_exit', 'target'),
        ]

        const nodes = [
          createMockNode('start', 'Start'),
          createMockNode('loop', 'Loop Control'),
          createMockNode('loop_body', 'Loop Body'),
          createMockNode('success_exit', 'Success Path'),
          createMockNode('error_exit', 'Error Path'),
          createMockNode('target', 'Final Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(5)
        expect(result).toContainEqual(expect.objectContaining({ id: 'start', name: 'Start' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'loop', name: 'Loop Control' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'loop_body', name: 'Loop Body' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'success_exit', name: 'Success Path' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'error_exit', name: 'Error Path' }))
      })
    })

    describe('Nested Control Flow', () => {
      it('handles condition inside loop', () => {
        // Arrange - Loop containing a condition
        const edges = [
          createMockEdge('e1', 'start', 'loop'),
          createMockEdge('e2', 'loop', 'condition', 'loop'),
          createMockEdge('e3', 'condition', 'pathA', 'true'),
          createMockEdge('e4', 'condition', 'pathB', 'false'),
          createMockEdge('e5', 'pathA', 'converge'),
          createMockEdge('e6', 'pathB', 'converge'),
          createMockEdge('e7', 'converge', 'target'),
          createMockEdge('e8', 'target', 'loop'), // Back to loop
        ]

        const nodes = [
          createMockNode('start', 'Start'),
          createMockNode('loop', 'Loop Control'),
          createMockNode('condition', 'Loop Condition'),
          createMockNode('pathA', 'Path A'),
          createMockNode('pathB', 'Path B'),
          createMockNode('converge', 'Merge'),
          createMockNode('target', 'Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert - Should discover all paths including both condition branches
        expect(result.length).toBeGreaterThan(0)
        expect(result.map((n) => n.id)).toContain('start')
        expect(result.map((n) => n.id)).toContain('loop')
        expect(result.map((n) => n.id)).toContain('condition')
        expect(result.map((n) => n.id)).toContain('pathA')
        expect(result.map((n) => n.id)).toContain('pathB')
        expect(result.map((n) => n.id)).toContain('converge')
      })

      it('handles loop inside condition branch', () => {
        // Arrange - Condition where one branch contains a loop
        const edges = [
          createMockEdge('e1', 'start', 'condition'),
          createMockEdge('e2', 'condition', 'simple_path', 'true'),
          createMockEdge('e3', 'condition', 'loop', 'false'),
          createMockEdge('e4', 'loop', 'loop_body', 'loop'),
          createMockEdge('e5', 'loop_body', 'loop'),
          createMockEdge('e6', 'loop', 'loop_exit', 'done'),
          createMockEdge('e7', 'simple_path', 'target'),
          createMockEdge('e8', 'loop_exit', 'target'),
        ]

        const nodes = [
          createMockNode('start', 'Start'),
          createMockNode('condition', 'Branch Decision'),
          createMockNode('simple_path', 'Simple Path'),
          createMockNode('loop', 'Loop Control'),
          createMockNode('loop_body', 'Loop Body'),
          createMockNode('loop_exit', 'Loop Exit'),
          createMockNode('target', 'Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert
        expect(result).toHaveLength(6)
        expect(result.map((n) => n.id)).toContain('start')
        expect(result.map((n) => n.id)).toContain('condition')
        expect(result.map((n) => n.id)).toContain('simple_path')
        expect(result.map((n) => n.id)).toContain('loop')
        expect(result.map((n) => n.id)).toContain('loop_body')
        expect(result.map((n) => n.id)).toContain('loop_exit')
      })

      it('handles deeply nested control flow structures', () => {
        // Arrange - Complex: condition → loop → condition → converge
        const edges = [
          createMockEdge('e1', 'start', 'outer_condition'),
          createMockEdge('e2', 'outer_condition', 'fast_path', 'fast'),
          createMockEdge('e3', 'outer_condition', 'loop', 'slow'),
          createMockEdge('e4', 'loop', 'inner_condition', 'loop'),
          createMockEdge('e5', 'inner_condition', 'branch_a', 'true'),
          createMockEdge('e6', 'inner_condition', 'branch_b', 'false'),
          createMockEdge('e7', 'branch_a', 'loop_converge'),
          createMockEdge('e8', 'branch_b', 'loop_converge'),
          createMockEdge('e9', 'loop_converge', 'loop'), // Back to loop
          createMockEdge('e10', 'loop', 'loop_exit', 'done'),
          createMockEdge('e11', 'fast_path', 'final_converge'),
          createMockEdge('e12', 'loop_exit', 'final_converge'),
          createMockEdge('e13', 'final_converge', 'target'),
        ]

        const nodes = [
          createMockNode('start', 'Start'),
          createMockNode('outer_condition', 'Route Decision'),
          createMockNode('fast_path', 'Fast Track'),
          createMockNode('loop', 'Processing Loop'),
          createMockNode('inner_condition', 'Item Check'),
          createMockNode('branch_a', 'Process A'),
          createMockNode('branch_b', 'Process B'),
          createMockNode('loop_converge', 'Merge Items'),
          createMockNode('loop_exit', 'Loop Done'),
          createMockNode('final_converge', 'Final Merge'),
          createMockNode('target', 'Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert - All nodes should be discovered
        expect(result).toHaveLength(10)
        const resultIds = result.map((n) => n.id)
        expect(resultIds).toContain('start')
        expect(resultIds).toContain('outer_condition')
        expect(resultIds).toContain('fast_path')
        expect(resultIds).toContain('loop')
        expect(resultIds).toContain('inner_condition')
        expect(resultIds).toContain('branch_a')
        expect(resultIds).toContain('branch_b')
        expect(resultIds).toContain('loop_converge')
        expect(resultIds).toContain('loop_exit')
        expect(resultIds).toContain('final_converge')
      })
    })

    describe('Edge Cases and Error Handling', () => {
      it('handles disconnected control flow subgraphs', () => {
        // Arrange - Target connected to some nodes, but other control flow exists separately
        const edges = [
          // Connected to target
          createMockEdge('e1', 'connected', 'target'),
          // Separate control flow
          createMockEdge('e2', 'separate_start', 'condition'),
          createMockEdge('e3', 'condition', 'branch_a', 'true'),
          createMockEdge('e4', 'condition', 'branch_b', 'false'),
          createMockEdge('e5', 'branch_a', 'separate_end'),
          createMockEdge('e6', 'branch_b', 'separate_end'),
        ]

        const nodes = [
          createMockNode('connected', 'Connected Node'),
          createMockNode('target', 'Target'),
          createMockNode('separate_start', 'Separate Start'),
          createMockNode('condition', 'Separate Condition'),
          createMockNode('branch_a', 'Separate Branch A'),
          createMockNode('branch_b', 'Separate Branch B'),
          createMockNode('separate_end', 'Separate End'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert - Should only find connected ancestors
        expect(result).toHaveLength(1)
        expect(result).toContainEqual(expect.objectContaining({ id: 'connected', name: 'Connected Node' }))
      })

      it('handles control flow with missing nodes', () => {
        // Arrange - Edges reference nodes that don't exist in nodes array
        const edges = [
          createMockEdge('e1', 'existing', 'condition'),
          createMockEdge('e2', 'condition', 'missing_true', 'true'), // missing_true not in nodes
          createMockEdge('e3', 'condition', 'existing_false', 'false'),
          createMockEdge('e4', 'existing_false', 'target'),
          createMockEdge('e5', 'missing_true', 'target'), // Edge from missing node
        ]

        const nodes = [
          createMockNode('existing', 'Existing Node'),
          createMockNode('condition', 'Condition'),
          createMockNode('existing_false', 'Existing False'),
          createMockNode('target', 'Target'),
          // missing_true is not in nodes array
        ]

        // Act & Assert - Should not throw error
        expect(() => {
          const result = getAncestorNodes('target', edges, nodes)
          // Should find the existing nodes
          expect(result.length).toBeGreaterThan(0)
          expect(result.map((n) => n.id)).toContain('existing')
          expect(result.map((n) => n.id)).toContain('condition')
          expect(result.map((n) => n.id)).toContain('existing_false')
          // missing_true should be handled gracefully (fallback to ID)
          expect(result.map((n) => n.id)).toContain('missing_true')
        }).not.toThrow()
      })

      it('handles empty control flow graphs', () => {
        // Arrange
        const edges: Edge[] = []
        const nodes: Node[] = [createMockNode('isolated', 'Isolated Node')]

        // Act
        const result = getAncestorNodes('isolated', edges, nodes)

        // Assert
        expect(result).toHaveLength(0)
      })

      it('handles control flow with self-loops', () => {
        // Arrange - Node that connects to itself
        const edges = [
          createMockEdge('e1', 'start', 'self_loop'),
          createMockEdge('e2', 'self_loop', 'self_loop'), // Self loop
          createMockEdge('e3', 'self_loop', 'target'),
        ]

        const nodes = [
          createMockNode('start', 'Start'),
          createMockNode('self_loop', 'Self Loop'),
          createMockNode('target', 'Target'),
        ]

        // Act
        const result = getAncestorNodes('target', edges, nodes)

        // Assert - Should handle self-loop without infinite recursion
        expect(result).toHaveLength(2)
        expect(result).toContainEqual(expect.objectContaining({ id: 'start', name: 'Start' }))
        expect(result).toContainEqual(expect.objectContaining({ id: 'self_loop', name: 'Self Loop' }))
      })
    })

    // NEW TESTS: Control Flow Extensions for condition node pre-resolved control.next_port
    describe('Control Flow Extensions (Condition Node Pre-Resolved)', () => {
      // Helper functions for creating test data structures with enhanced type information
      function createMockNodeWithType(id: string, name: string, options: { type?: string } = {}): Node {
        return {
          id,
          data: {
            name,
            type: options.type || 'task',
          },
          type: options.type || 'task',
          position: { x: 0, y: 0 },
        }
      }

      describe('Control Flow Node Type Detection', () => {
        it('returns type and portTowardTarget for condition node ancestors', () => {
          // Arrange
          const edges = [
            createMockEdge('e1', 'condition_1', 'target', 'true'),
            createMockEdge('e2', 'condition_1', 'alt_path', 'false'),
          ]

          const nodes = [
            createMockNodeWithType('condition_1', 'Check Environment', { type: 'condition' }),
            createMockNodeWithType('target', 'Target Step', { type: 'task' }),
            createMockNodeWithType('alt_path', 'Alt Path', { type: 'task' }),
          ]

          // Act
          const result = getAncestorNodes('target', edges, nodes)

          // Assert - THIS WILL FAIL until implementation is updated
          expect(result).toHaveLength(1)
          expect(result[0]).toEqual({
            id: 'condition_1',
            name: 'Check Environment',
            type: 'condition',
            portTowardTarget: 'true', // From edge sourceHandle
          })
        })

        it('returns type and portTowardTarget for loop node ancestors', () => {
          // Arrange
          const edges = [
            createMockEdge('e1', 'loop_1', 'target', 'done'),
            createMockEdge('e2', 'loop_1', 'loop_body', 'loop'),
          ]

          const nodes = [
            createMockNodeWithType('loop_1', 'Process Items', { type: 'loop' }),
            createMockNodeWithType('target', 'Target Step', { type: 'task' }),
            createMockNodeWithType('loop_body', 'Loop Body', { type: 'task' }),
          ]

          // Act
          const result = getAncestorNodes('target', edges, nodes)

          // Assert - THIS WILL FAIL until implementation is updated
          expect(result).toHaveLength(1)
          expect(result[0]).toEqual({
            id: 'loop_1',
            name: 'Process Items',
            type: 'loop',
            portTowardTarget: 'done', // From edge sourceHandle
          })
        })

        it('returns type but undefined portTowardTarget for regular task ancestors', () => {
          // Arrange
          const edges = [
            createMockEdge('e1', 'task_1', 'target'), // No sourceHandle
          ]

          const nodes = [
            createMockNodeWithType('task_1', 'Setup Task', { type: 'task' }),
            createMockNodeWithType('target', 'Target Step', { type: 'task' }),
          ]

          // Act
          const result = getAncestorNodes('target', edges, nodes)

          // Assert - THIS WILL FAIL until implementation is updated
          expect(result).toHaveLength(1)
          expect(result[0]).toEqual({
            id: 'task_1',
            name: 'Setup Task',
            type: 'task',
            portTowardTarget: undefined, // No sourceHandle = no control flow
          })
        })

        it('uses node.data.type with fallback to node.type', () => {
          // Arrange
          const edges = [createMockEdge('e1', 'unknown_node', 'target')]

          const nodes = [
            {
              id: 'unknown_node',
              data: { name: 'Unknown' }, // No data.type
              type: 'custom-type', // React Flow node type
              position: { x: 0, y: 0 },
            },
            createMockNodeWithType('target', 'Target', { type: 'task' }),
          ] as Node[]

          // Act
          const result = getAncestorNodes('target', edges, nodes)

          // Assert - THIS WILL FAIL until implementation is updated to use data.type || node.type
          expect(result).toHaveLength(1)
          expect(result[0]).toEqual({
            id: 'unknown_node',
            name: 'Unknown',
            type: 'custom-type', // Should fall back to node.type
            portTowardTarget: undefined,
          })
        })
      })

      describe('Mixed Control Flow Scenarios', () => {
        it('handles mixed control flow and regular nodes correctly', () => {
          // Arrange - setup → condition → [true: task, false: loop] → converge → target
          const edges = [
            createMockEdge('e1', 'setup', 'condition_1'),
            createMockEdge('e2', 'condition_1', 'task_true', 'true'),
            createMockEdge('e3', 'condition_1', 'loop_1', 'false'),
            createMockEdge('e4', 'task_true', 'converge_1'),
            createMockEdge('e5', 'loop_1', 'converge_1', 'done'),
            createMockEdge('e6', 'converge_1', 'target'),
          ]

          const nodes = [
            createMockNodeWithType('setup', 'Setup', { type: 'task' }),
            createMockNodeWithType('condition_1', 'Check', { type: 'condition' }),
            createMockNodeWithType('task_true', 'True Task', { type: 'task' }),
            createMockNodeWithType('loop_1', 'Loop', { type: 'loop' }),
            createMockNodeWithType('converge_1', 'Converge', { type: 'converge' }),
            createMockNodeWithType('target', 'Target', { type: 'task' }),
          ]

          // Act
          const result = getAncestorNodes('target', edges, nodes)

          // Assert - THIS WILL FAIL until implementation is updated
          expect(result).toHaveLength(5)

          const conditionAncestor = result.find((n) => n.id === 'condition_1')
          expect(conditionAncestor).toEqual({
            id: 'condition_1',
            name: 'Check',
            type: 'condition',
            portTowardTarget: 'true',
          })

          const loopAncestor = result.find((n) => n.id === 'loop_1')
          expect(loopAncestor).toEqual({
            id: 'loop_1',
            name: 'Loop',
            type: 'loop',
            portTowardTarget: 'done', // Edge to converge has 'done' handle
          })

          const taskAncestor = result.find((n) => n.id === 'setup')
          expect(taskAncestor).toEqual({
            id: 'setup',
            name: 'Setup',
            type: 'task',
            portTowardTarget: undefined,
          })
        })
      })

      describe('Edge Cases', () => {
        it('excludes trigger nodes but includes their type info for debugging', () => {
          // Arrange
          const edges = [createMockEdge('e1', 'trigger-0', 'task_1'), createMockEdge('e2', 'task_1', 'target')]

          const nodes = [
            createMockNodeWithType('trigger-0', 'Manual Trigger', { type: 'trigger' }),
            createMockNodeWithType('task_1', 'Task', { type: 'task' }),
            createMockNodeWithType('target', 'Target', { type: 'task' }),
          ]

          // Act
          const result = getAncestorNodes('target', edges, nodes)

          // Assert - triggers still excluded, only task_1 should be returned
          expect(result).toHaveLength(1)
          expect(result[0]).toEqual({
            id: 'task_1',
            name: 'Task',
            type: 'task',
            portTowardTarget: undefined,
          })
        })

        it('handles loop node with sourceHandle: loop has portTowardTarget: loop', () => {
          // Arrange
          const edges = [createMockEdge('e1', 'loop_1', 'target', 'loop')]

          const nodes = [
            createMockNodeWithType('loop_1', 'Loop Control', { type: 'loop' }),
            createMockNodeWithType('target', 'Target Step', { type: 'task' }),
          ]

          // Act
          const result = getAncestorNodes('target', edges, nodes)

          // Assert - THIS WILL FAIL until implementation is updated
          expect(result).toHaveLength(1)
          expect(result[0]).toEqual({
            id: 'loop_1',
            name: 'Loop Control',
            type: 'loop',
            portTowardTarget: 'loop', // Should preserve 'loop' handle (mapped later to 'iterate')
          })
        })
      })
    })
  })
})
