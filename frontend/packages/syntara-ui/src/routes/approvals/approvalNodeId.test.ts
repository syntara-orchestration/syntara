import {
  canvasNodeIdFromApprovalNodeId,
  findApprovalForCanvasNode,
  findApprovalIndexForCanvasNode,
  findNodeByApprovalNodeId,
  lookupMapByApprovalNodeId,
  matchesApprovalNodeId,
} from './approvalNodeId'

describe('canvasNodeIdFromApprovalNodeId', () => {
  it('returns a plain canvas id unchanged', () => {
    expect(canvasNodeIdFromApprovalNodeId('a1')).toBe('a1')
  })

  it('strips a loop-iteration suffix', () => {
    expect(canvasNodeIdFromApprovalNodeId('a1_iter_0')).toBe('a1')
    expect(canvasNodeIdFromApprovalNodeId('a1_iter_12')).toBe('a1')
  })

  it('strips a composite activity key', () => {
    expect(canvasNodeIdFromApprovalNodeId('a1#iter-1')).toBe('a1')
  })

  it('does not strip a non-numeric _iter_ suffix', () => {
    expect(canvasNodeIdFromApprovalNodeId('a1_iter_n')).toBe('a1_iter_n')
  })
})

describe('matchesApprovalNodeId', () => {
  it('matches exact ids', () => {
    expect(matchesApprovalNodeId('a1', 'a1')).toBe(true)
  })

  it('matches a loop-iteration approval to the canvas node', () => {
    expect(matchesApprovalNodeId('a1_iter_1', 'a1')).toBe(true)
  })

  it('matches a loop-iteration approval to a composite activity key', () => {
    expect(matchesApprovalNodeId('a1_iter_1', 'a1#iter-1')).toBe(true)
  })

  it('does not match a different canvas node', () => {
    expect(matchesApprovalNodeId('a1_iter_1', 'a10')).toBe(false)
    expect(matchesApprovalNodeId('a1', 'a2')).toBe(false)
  })
})

describe('findApprovalForCanvasNode', () => {
  const approvals = [
    { id: 'first', approval_node_id: 'a1_iter_0' },
    { id: 'other', approval_node_id: 'a2' },
  ]

  it('finds a suffixed approval by canvas node id', () => {
    expect(findApprovalForCanvasNode(approvals, 'a1')?.id).toBe('first')
  })

  it('returns undefined when no approval matches', () => {
    expect(findApprovalForCanvasNode(approvals, 'missing')).toBeUndefined()
  })
})

describe('findApprovalIndexForCanvasNode', () => {
  const approvals = [{ approval_node_id: 'gate_iter_1' }]

  it('returns the matching index', () => {
    expect(findApprovalIndexForCanvasNode(approvals, 'gate')).toBe(0)
  })

  it('returns -1 when nothing matches', () => {
    expect(findApprovalIndexForCanvasNode(approvals, 'other')).toBe(-1)
  })
})

describe('findNodeByApprovalNodeId', () => {
  const nodes = [{ id: 'a1', prompt: 'ok' }]

  it('finds the canvas node from a suffixed approval id', () => {
    expect(findNodeByApprovalNodeId(nodes, 'a1_iter_2')).toEqual(nodes[0])
  })
})

describe('lookupMapByApprovalNodeId', () => {
  const map = new Map([['a1', 'Approve server']])

  it('resolves names keyed by canvas id', () => {
    expect(lookupMapByApprovalNodeId(map, 'a1_iter_0')).toBe('Approve server')
  })

  it('returns undefined for a missing map or id', () => {
    expect(lookupMapByApprovalNodeId(undefined, 'a1')).toBeUndefined()
    expect(lookupMapByApprovalNodeId(map, null)).toBeUndefined()
  })
})
