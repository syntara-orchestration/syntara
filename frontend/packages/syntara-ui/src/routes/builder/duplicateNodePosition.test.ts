import type { Node } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import { findDuplicatePosition } from './duplicateNodePosition'

const GAP = 120
const DEFAULT_W = 300
const DEFAULT_H = 60

function node(id: string, pos: { x: number; y: number }, measured?: { width: number; height: number }): Node {
  return {
    id,
    position: pos,
    data: {},
    measured: measured ?? { width: DEFAULT_W, height: DEFAULT_H },
  }
}

describe('findDuplicatePosition', () => {
  it('returns preferred slot to the right when no other measured nodes exist', () => {
    const orig = node('orig', { x: 0, y: 0 })
    const result = findDuplicatePosition(orig, [orig])
    const preferredX = 0 + DEFAULT_W + GAP
    expect(result).toEqual({ x: preferredX, y: 0 })
  })

  it('uses default width and height when original has no measured size', () => {
    const orig = { id: 'orig', position: { x: 10, y: 20 }, data: {} } as Node
    const result = findDuplicatePosition(orig, [orig])
    expect(result.x).toBe(10 + DEFAULT_W + GAP)
    expect(result.y).toBe(20)
  })

  it('ignores nodes without measured dimensions for collision', () => {
    const orig = node('orig', { x: 0, y: 0 })
    const unmeasured = { id: 'u', position: { x: 500, y: 0 }, data: {} } as Node
    const result = findDuplicatePosition(orig, [orig, unmeasured])
    expect(result).toEqual({ x: DEFAULT_W + GAP, y: 0 })
  })

  it('skips to the next horizontal slot when the preferred position is blocked', () => {
    const orig = node('orig', { x: 0, y: 0 })
    const preferredX = DEFAULT_W + GAP
    const blocker = node('block', { x: preferredX, y: 0 })
    const result = findDuplicatePosition(orig, [orig, blocker])
    expect(result.x).toBe(preferredX + DEFAULT_W + GAP)
    expect(result.y).toBe(0)
  })

  it('does not treat the original node as an obstacle', () => {
    const orig = node('orig', { x: 100, y: 0 })
    const result = findDuplicatePosition(orig, [orig])
    expect(result.x).toBe(100 + DEFAULT_W + GAP)
  })

  it('uses the next row when the current row is fully blocked along the scan', () => {
    const orig = node('orig', { x: 0, y: 0 })
    const preferredX = DEFAULT_W + GAP
    const row0: Node[] = []
    for (let i = 0; i < 20; i++) {
      row0.push(node(`r0-${i}`, { x: preferredX + i * (DEFAULT_W + GAP), y: 0 }))
    }
    const result = findDuplicatePosition(orig, [orig, ...row0])
    const row1Y = DEFAULT_H + GAP
    expect(result.y).toBe(row1Y)
    expect(result.x).toBe(preferredX)
  })

  it('falls back to rightmostX when every scan row exhausts without a free slot', () => {
    const orig = node('orig', { x: 0, y: 0 })
    const preferredX = DEFAULT_W + GAP
    const others: Node[] = []
    for (let row = 0; row < 10; row++) {
      const y = orig.position.y + row * (DEFAULT_H + GAP)
      for (let i = 0; i < 20; i++) {
        const x = preferredX + i * (DEFAULT_W + GAP)
        others.push(node(`b-${row}-${i}`, { x, y }))
      }
    }
    const result = findDuplicatePosition(orig, [orig, ...others])
    const rightmostX = others.reduce((max, n) => Math.max(max, n.position.x + DEFAULT_W + GAP), preferredX)
    expect(result).toEqual({ x: rightmostX, y: orig.position.y })
  })
})
