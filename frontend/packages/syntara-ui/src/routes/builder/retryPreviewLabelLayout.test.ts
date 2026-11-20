import { describe, expect, it } from 'vitest'

import type { RetryPreviewCanvasState } from './retryPreviewCanvasState'
import {
  getRetryPreviewLabelPlacements,
  RETRY_LABEL_BASE_OFFSET,
  RETRY_LABEL_HEIGHT,
  RETRY_LABEL_LANE_GAP,
  type RetryPreviewLayoutNode,
} from './retryPreviewLabelLayout'

const NODE_HEIGHT = 120
const NODE_WIDTH = 300
const MAX_TOP_OFFSET = RETRY_LABEL_BASE_OFFSET + RETRY_LABEL_HEIGHT + RETRY_LABEL_LANE_GAP

function node(id: string, x: number, y: number): RetryPreviewLayoutNode {
  return { id, position: { x, y }, width: NODE_WIDTH, height: NODE_HEIGHT }
}

function states(...ids: string[]): Map<string, RetryPreviewCanvasState> {
  return new Map(ids.map((id, index) => [id, index === 0 ? 'origin' : 'will-retry']))
}

describe('getRetryPreviewLabelPlacements', () => {
  it('keeps an isolated retry label centered above its step', () => {
    const placements = getRetryPreviewLabelPlacements([node('step-a', 0, 200)], states('step-a'), 1)

    expect(placements.get('step-a')).toEqual({ offset: RETRY_LABEL_BASE_OFFSET, align: 'center', side: 'top' })
  })

  it('places a stacked step’s label to the side instead of several rows above', () => {
    const placements = getRetryPreviewLabelPlacements(
      [node('wait', 0, 0), node('rest-api', 0, NODE_HEIGHT + 10)],
      states('rest-api'),
      1
    )
    const restApi = placements.get('rest-api')

    expect(['left', 'right']).toContain(restApi?.side)
    expect(restApi?.offset).toBe(RETRY_LABEL_BASE_OFFSET)
    expect(restApi?.align).toBe('start')
  })

  it('does not stack a top label farther than one extra lane', () => {
    const placements = getRetryPreviewLabelPlacements(
      [
        node('above-left', 0, 0),
        node('above-right', NODE_WIDTH + 40, 0),
        node('target', NODE_WIDTH / 2, NODE_HEIGHT + 8),
      ],
      states('target'),
      1
    )
    const target = placements.get('target')

    expect(target).toBeDefined()
    if (target?.side === 'top') {
      expect(target.offset).toBeLessThanOrEqual(MAX_TOP_OFFSET)
    } else {
      expect(target?.offset).toBe(RETRY_LABEL_BASE_OFFSET)
    }
  })

  it('uses parent-relative coordinates so nested steps stay attached', () => {
    const placements = getRetryPreviewLabelPlacements(
      [
        { id: 'parent', position: { x: 400, y: 80 }, width: 320, height: 200 },
        { id: 'child', position: { x: 10, y: 0 }, parentId: 'parent', width: 280, height: 80 },
      ],
      states('child'),
      1
    )

    expect(placements.get('child')).toEqual({ offset: RETRY_LABEL_BASE_OFFSET, align: 'center', side: 'top' })
  })
})
