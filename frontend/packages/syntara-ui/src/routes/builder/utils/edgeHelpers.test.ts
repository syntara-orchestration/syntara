import { EdgeHandleEnum } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

import type { EdgeConnection } from '../types/edge'

import {
  getButtonEdgeId,
  getPendingEdgeId,
  getPendingTargetNodeId,
  getPlaceholderNodeId,
  getUpstreamNodeIds,
  handleToV2Port,
  isApprovalHandle,
  isBranchHandle,
  isConditionalHandle,
  isFormPromptHandle,
  isLoopHandle,
  v2PortToHandle,
  v2TargetPortToHandle,
} from './edgeHelpers'

describe('edgeHelpers', () => {
  describe('isConditionalHandle', () => {
    it('returns true for true handle', () => {
      expect(isConditionalHandle(EdgeHandleEnum.TRUE)).toBe(true)
    })

    it('returns true for false handle', () => {
      expect(isConditionalHandle(EdgeHandleEnum.FALSE)).toBe(true)
    })

    it('returns false for other handles', () => {
      expect(isConditionalHandle(EdgeHandleEnum.SOURCE)).toBe(false)
      expect(isConditionalHandle(EdgeHandleEnum.TARGET)).toBe(false)
      expect(isConditionalHandle(EdgeHandleEnum.APPROVED)).toBe(false)
      expect(isConditionalHandle(EdgeHandleEnum.REJECTED)).toBe(false)
    })

    it('returns false for undefined', () => {
      expect(isConditionalHandle(undefined)).toBe(false)
    })
  })

  describe('isApprovalHandle', () => {
    it('returns true for approved handle', () => {
      expect(isApprovalHandle(EdgeHandleEnum.APPROVED)).toBe(true)
    })

    it('returns true for rejected handle', () => {
      expect(isApprovalHandle(EdgeHandleEnum.REJECTED)).toBe(true)
    })

    it('returns false for other handles', () => {
      expect(isApprovalHandle(EdgeHandleEnum.SOURCE)).toBe(false)
      expect(isApprovalHandle(EdgeHandleEnum.TARGET)).toBe(false)
      expect(isApprovalHandle(EdgeHandleEnum.TRUE)).toBe(false)
      expect(isApprovalHandle(EdgeHandleEnum.FALSE)).toBe(false)
    })

    it('returns false for undefined', () => {
      expect(isApprovalHandle(undefined)).toBe(false)
    })
  })

  describe('isFormPromptHandle', () => {
    it('returns true for submitted and fallback handles', () => {
      expect(isFormPromptHandle(EdgeHandleEnum.SUBMITTED)).toBe(true)
      expect(isFormPromptHandle(EdgeHandleEnum.FALLBACK)).toBe(true)
    })

    it('returns false for unrelated handles', () => {
      expect(isFormPromptHandle(EdgeHandleEnum.APPROVED)).toBe(false)
      expect(isFormPromptHandle(undefined)).toBe(false)
    })
  })

  describe('isLoopHandle', () => {
    it('returns true for loop handle', () => {
      expect(isLoopHandle(EdgeHandleEnum.LOOP)).toBe(true)
    })

    it('returns true for done handle', () => {
      expect(isLoopHandle(EdgeHandleEnum.DONE)).toBe(true)
    })

    it('returns false for other handles', () => {
      expect(isLoopHandle(EdgeHandleEnum.SOURCE)).toBe(false)
      expect(isLoopHandle(EdgeHandleEnum.TARGET)).toBe(false)
      expect(isLoopHandle(EdgeHandleEnum.TRUE)).toBe(false)
      expect(isLoopHandle(EdgeHandleEnum.FALSE)).toBe(false)
    })

    it('returns false for undefined', () => {
      expect(isLoopHandle(undefined)).toBe(false)
    })
  })

  describe('isBranchHandle', () => {
    it('returns true for conditional handles', () => {
      expect(isBranchHandle(EdgeHandleEnum.TRUE)).toBe(true)
      expect(isBranchHandle(EdgeHandleEnum.FALSE)).toBe(true)
    })

    it('returns true for approval handles', () => {
      expect(isBranchHandle(EdgeHandleEnum.APPROVED)).toBe(true)
      expect(isBranchHandle(EdgeHandleEnum.REJECTED)).toBe(true)
    })

    it('returns true for loop handles', () => {
      expect(isBranchHandle(EdgeHandleEnum.LOOP)).toBe(true)
      expect(isBranchHandle(EdgeHandleEnum.DONE)).toBe(true)
    })

    it('returns true for switch case handles', () => {
      expect(isBranchHandle('case_0')).toBe(true)
      expect(isBranchHandle('case_1')).toBe(true)
      expect(isBranchHandle('case_99')).toBe(true)
    })

    it('returns true for switch default handle', () => {
      expect(isBranchHandle(EdgeHandleEnum.DEFAULT)).toBe(true)
    })

    it('returns false for other handles', () => {
      expect(isBranchHandle(EdgeHandleEnum.SOURCE)).toBe(false)
      expect(isBranchHandle(EdgeHandleEnum.TARGET)).toBe(false)
    })

    it('returns false for undefined', () => {
      expect(isBranchHandle(undefined)).toBe(false)
    })
  })

  describe('getButtonEdgeId', () => {
    it('generates simple ID for non-branch handles', () => {
      expect(getButtonEdgeId('node-1')).toBe('button-node-1')
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.SOURCE)).toBe('button-node-1')
    })

    it('generates handle-specific ID for conditional handles', () => {
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.TRUE)).toBe('button-node-1-true')
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.FALSE)).toBe('button-node-1-false')
    })

    it('generates handle-specific ID for approval handles', () => {
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.APPROVED)).toBe('button-node-1-approved')
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.REJECTED)).toBe('button-node-1-rejected')
    })

    it('generates handle-specific ID for loop handles', () => {
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.LOOP)).toBe('button-node-1-loop')
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.DONE)).toBe('button-node-1-done')
    })

    it('generates handle-specific ID for switch handles', () => {
      expect(getButtonEdgeId('node-1', 'case_0')).toBe('button-node-1-case_0')
      expect(getButtonEdgeId('node-1', 'case_1')).toBe('button-node-1-case_1')
      expect(getButtonEdgeId('node-1', EdgeHandleEnum.DEFAULT)).toBe('button-node-1-default')
    })
  })

  describe('getPlaceholderNodeId', () => {
    it('generates simple ID for non-branch handles', () => {
      expect(getPlaceholderNodeId('node-1')).toBe('placeholder-node-1')
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.SOURCE)).toBe('placeholder-node-1')
    })

    it('generates handle-specific ID for conditional handles', () => {
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.TRUE)).toBe('placeholder-node-1-true')
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.FALSE)).toBe('placeholder-node-1-false')
    })

    it('generates handle-specific ID for approval handles', () => {
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.APPROVED)).toBe('placeholder-node-1-approved')
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.REJECTED)).toBe('placeholder-node-1-rejected')
    })

    it('generates handle-specific ID for loop handles', () => {
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.LOOP)).toBe('placeholder-node-1-loop')
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.DONE)).toBe('placeholder-node-1-done')
    })

    it('generates handle-specific ID for switch handles', () => {
      expect(getPlaceholderNodeId('node-1', 'case_0')).toBe('placeholder-node-1-case_0')
      expect(getPlaceholderNodeId('node-1', 'case_1')).toBe('placeholder-node-1-case_1')
      expect(getPlaceholderNodeId('node-1', EdgeHandleEnum.DEFAULT)).toBe('placeholder-node-1-default')
    })
  })

  describe('getPendingTargetNodeId', () => {
    it('generates pending target node ID', () => {
      expect(getPendingTargetNodeId('node-1')).toBe('pending-target-node-1')
      expect(getPendingTargetNodeId('condition-abc')).toBe('pending-target-condition-abc')
    })
  })

  describe('getPendingEdgeId', () => {
    it('generates pending edge ID', () => {
      expect(getPendingEdgeId('node-1')).toBe('pending-node-1')
      expect(getPendingEdgeId('task-xyz')).toBe('pending-task-xyz')
    })
  })

  describe('v2PortToHandle - converts v2 API ports to React Flow handles', () => {
    it('converts "iterate" to "loop"', () => {
      expect(v2PortToHandle('iterate')).toBe(EdgeHandleEnum.LOOP)
    })

    it('converts "complete" to "done"', () => {
      expect(v2PortToHandle('complete')).toBe(EdgeHandleEnum.DONE)
    })

    it('passes through "true" unchanged', () => {
      expect(v2PortToHandle('true')).toBe(EdgeHandleEnum.TRUE)
    })

    it('passes through "false" unchanged', () => {
      expect(v2PortToHandle('false')).toBe(EdgeHandleEnum.FALSE)
    })

    it('passes through "approved" unchanged', () => {
      expect(v2PortToHandle('approved')).toBe(EdgeHandleEnum.APPROVED)
    })

    it('passes through "rejected" unchanged', () => {
      expect(v2PortToHandle('rejected')).toBe(EdgeHandleEnum.REJECTED)
    })

    it('returns "source" for undefined', () => {
      expect(v2PortToHandle(undefined)).toBe(EdgeHandleEnum.SOURCE)
    })

    it('returns "source" for null', () => {
      expect(v2PortToHandle(null)).toBe(EdgeHandleEnum.SOURCE)
    })

    it('returns "source" for empty string', () => {
      expect(v2PortToHandle('')).toBe(EdgeHandleEnum.SOURCE)
    })
  })

  describe('handleToV2Port - converts React Flow handles to v2 API ports', () => {
    it('converts "loop" to "iterate"', () => {
      expect(handleToV2Port(EdgeHandleEnum.LOOP)).toBe('iterate')
    })

    it('converts "done" to "complete"', () => {
      expect(handleToV2Port(EdgeHandleEnum.DONE)).toBe('complete')
    })

    it('passes through "true" unchanged', () => {
      expect(handleToV2Port(EdgeHandleEnum.TRUE)).toBe(EdgeHandleEnum.TRUE)
    })

    it('passes through "false" unchanged', () => {
      expect(handleToV2Port(EdgeHandleEnum.FALSE)).toBe(EdgeHandleEnum.FALSE)
    })

    it('passes through "approved" unchanged', () => {
      expect(handleToV2Port(EdgeHandleEnum.APPROVED)).toBe(EdgeHandleEnum.APPROVED)
    })

    it('passes through "rejected" unchanged', () => {
      expect(handleToV2Port(EdgeHandleEnum.REJECTED)).toBe(EdgeHandleEnum.REJECTED)
    })

    it('returns undefined for "source"', () => {
      expect(handleToV2Port(EdgeHandleEnum.SOURCE)).toBeUndefined()
    })

    it('returns undefined for "target"', () => {
      expect(handleToV2Port(EdgeHandleEnum.TARGET)).toBeUndefined()
    })

    it('returns undefined for undefined', () => {
      expect(handleToV2Port(undefined)).toBeUndefined()
    })

    it('returns undefined for null', () => {
      expect(handleToV2Port(null)).toBeUndefined()
    })

    it('passes switch case handles through as v2 ports', () => {
      expect(handleToV2Port('case_0')).toBe('case_0')
      expect(handleToV2Port('case_1')).toBe('case_1')
      expect(handleToV2Port('case_99')).toBe('case_99')
    })

    it('converts "end" to "iterate" for loop feedback edges', () => {
      expect(handleToV2Port(EdgeHandleEnum.END)).toBe('iterate')
    })

    it('passes switch default handle through as v2 port', () => {
      expect(handleToV2Port(EdgeHandleEnum.DEFAULT)).toBe('default')
    })
  })

  describe('Round-trip conversion - v2 → React Flow → v2', () => {
    it('iterate → loop → iterate', () => {
      const v2Port = 'iterate'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })

    it('complete → done → complete', () => {
      const v2Port = 'complete'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })

    it('true → true → true', () => {
      const v2Port = 'true'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })

    it('false → false → false', () => {
      const v2Port = 'false'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })

    it('approved → approved → approved', () => {
      const v2Port = 'approved'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })

    it('rejected → rejected → rejected', () => {
      const v2Port = 'rejected'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })

    it('undefined → source → undefined', () => {
      const v2Port = undefined
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBeUndefined()
    })

    it('case_0 → case_0 → case_0', () => {
      const v2Port = 'case_0'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })

    it('default → default → default', () => {
      const v2Port = 'default'
      const handle = v2PortToHandle(v2Port)
      const backToV2 = handleToV2Port(handle)
      expect(backToV2).toBe(v2Port)
    })
  })

  describe('getUpstreamNodeIds', () => {
    /** Helper to build an edge with minimal required fields. */
    function edge(source: string, target: string): EdgeConnection {
      return { id: `${source}->${target}`, source, target }
    }

    it('returns empty set for a root node with no incoming edges', () => {
      const edges = [edge('A', 'B'), edge('B', 'C')]
      const result = getUpstreamNodeIds('A', edges)
      expect(result.size).toBe(0)
    })

    it('returns empty set when the node is not referenced in any edge', () => {
      const edges = [edge('A', 'B'), edge('B', 'C')]
      const result = getUpstreamNodeIds('Z', edges)
      expect(result.size).toBe(0)
    })

    it('returns empty set when edge list is empty', () => {
      const result = getUpstreamNodeIds('A', [])
      expect(result.size).toBe(0)
    })

    it('returns single parent for A -> B', () => {
      const edges = [edge('A', 'B')]
      const result = getUpstreamNodeIds('B', edges)
      expect(result).toEqual(new Set(['A']))
    })

    it('returns all ancestors for a linear chain A -> B -> C', () => {
      const edges = [edge('A', 'B'), edge('B', 'C')]
      const result = getUpstreamNodeIds('C', edges)
      expect(result).toEqual(new Set(['A', 'B']))
    })

    it('returns both parents for a diamond/merge: A -> C, B -> C', () => {
      const edges = [edge('A', 'C'), edge('B', 'C')]
      const result = getUpstreamNodeIds('C', edges)
      expect(result).toEqual(new Set(['A', 'B']))
    })

    it('returns all ancestors for a diamond with shared root: A -> B, A -> C, B -> D, C -> D', () => {
      const edges = [edge('A', 'B'), edge('A', 'C'), edge('B', 'D'), edge('C', 'D')]
      const result = getUpstreamNodeIds('D', edges)
      expect(result).toEqual(new Set(['A', 'B', 'C']))
    })

    it('returns deep ancestors for a long chain: trigger -> A -> B -> C -> D', () => {
      const edges = [edge('trigger', 'A'), edge('A', 'B'), edge('B', 'C'), edge('C', 'D')]
      const result = getUpstreamNodeIds('D', edges)
      expect(result).toEqual(new Set(['trigger', 'A', 'B', 'C']))
    })

    it('excludes self-referencing edges', () => {
      const edges = [edge('A', 'B'), edge('B', 'B')]
      const result = getUpstreamNodeIds('B', edges)
      expect(result).toEqual(new Set(['A']))
    })

    it('does not include the starting node itself', () => {
      const edges = [edge('A', 'B'), edge('B', 'C')]
      const result = getUpstreamNodeIds('C', edges)
      expect(result.has('C')).toBe(false)
    })

    it('handles a complex DAG with multiple paths', () => {
      // Graph:
      //   A → B → D
      //   A → C → D
      //   D → E
      const edges = [edge('A', 'B'), edge('A', 'C'), edge('B', 'D'), edge('C', 'D'), edge('D', 'E')]
      const result = getUpstreamNodeIds('E', edges)
      expect(result).toEqual(new Set(['A', 'B', 'C', 'D']))
    })

    it('handles edges with extra properties without issue', () => {
      const edges: EdgeConnection[] = [
        { id: 'e1', source: 'A', target: 'B', sourceHandle: 'source', targetHandle: 'target' },
        { id: 'e2', source: 'B', target: 'C', sourceHandle: 'true', targetHandle: 'target' },
      ]
      const result = getUpstreamNodeIds('C', edges)
      expect(result).toEqual(new Set(['A', 'B']))
    })
  })

  describe('v2TargetPortToHandle - converts v2 API to_port to React Flow target handles', () => {
    it('converts "iterate" to END for loop feedback edges', () => {
      expect(v2TargetPortToHandle('iterate')).toBe(EdgeHandleEnum.END)
    })

    it('returns "target" for undefined', () => {
      expect(v2TargetPortToHandle(undefined)).toBe('target')
    })

    it('returns "target" for null', () => {
      expect(v2TargetPortToHandle(null)).toBe('target')
    })

    it('returns "target" for empty string', () => {
      expect(v2TargetPortToHandle('')).toBe('target')
    })

    it('passes through unknown ports unchanged', () => {
      expect(v2TargetPortToHandle('custom')).toBe('custom')
    })
  })

  describe('Loop feedback edge round-trip', () => {
    it('END handle → to_port "iterate" → END handle', () => {
      const v2Port = handleToV2Port(EdgeHandleEnum.END)
      expect(v2Port).toBe('iterate')
      const handle = v2TargetPortToHandle(v2Port)
      expect(handle).toBe(EdgeHandleEnum.END)
    })
  })
})
