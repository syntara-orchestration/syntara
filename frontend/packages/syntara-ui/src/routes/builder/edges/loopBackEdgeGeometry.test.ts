import { describe, expect, it } from 'vitest'

import { loopBackEdgeGeometryEqual, selectLoopBackEdgeGeometry } from './loopBackEdgeGeometry'

describe('selectLoopBackEdgeGeometry', () => {
  const nodes = [
    { id: 'loop-node', position: { x: 50, y: 25 }, measured: { height: 50 } },
    { id: 'body-node', position: { x: 250, y: 125 }, measured: { height: 50 } },
    { id: 'middle-node', position: { x: 150, y: 25 }, measured: { height: 100 } },
  ]

  it('includes loop, source, and intermediate body nodes in max bottom', () => {
    const geometry = selectLoopBackEdgeGeometry(nodes, {
      source: 'body-node',
      target: 'loop-node',
      sourceX: 300,
      sourceY: 150,
      targetX: 100,
      targetY: 50,
    })

    expect(geometry.loopBodyMaxBottom).toBe(175)
    expect(geometry.source).toEqual({ x: 250, y: 125, height: 50 })
    expect(geometry.target).toEqual({ x: 50, y: 25, height: 50 })
  })

  it('returns sourceY when nodes are missing geometry', () => {
    const geometry = selectLoopBackEdgeGeometry([{ id: 'loop-node', position: { x: 50, y: 25 } }], {
      source: 'body-node',
      target: 'loop-node',
      sourceX: 300,
      sourceY: 150,
      targetX: 100,
      targetY: 50,
    })

    expect(geometry.loopBodyMaxBottom).toBe(150)
    expect(geometry.source).toBeUndefined()
  })
})

describe('loopBackEdgeGeometryEqual', () => {
  it('detects changes in loop body max bottom', () => {
    const a = { loopBodyMaxBottom: 100, source: { x: 1, y: 2, height: 50 }, target: { x: 3, y: 4, height: 50 } }
    const b = { ...a, loopBodyMaxBottom: 120 }

    expect(loopBackEdgeGeometryEqual(a, a)).toBe(true)
    expect(loopBackEdgeGeometryEqual(a, b)).toBe(false)
  })
})
