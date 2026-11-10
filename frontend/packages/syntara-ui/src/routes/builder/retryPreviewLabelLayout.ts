import type { RetryPreviewCanvasState } from './retryPreviewCanvasState'

export type RetryLabelAlign = 'start' | 'center' | 'end'
export type RetryLabelSide = 'top' | 'left' | 'right'
export type RetryLabelPlacement = Readonly<{ offset: number; align: RetryLabelAlign; side: RetryLabelSide }>

export type RetryPreviewLayoutNode = Readonly<{
  id: string
  position: { x: number; y: number }
  parentId?: string
  width?: number | null
  height?: number | null
  measured?: { width?: number; height?: number }
}>

type RetryLabelBounds = Readonly<{ left: number; right: number; top: number; bottom: number }>
type RetryLabelEntry = Readonly<{
  nodeId: string
  nodeLeft: number
  nodeWidth: number
  nodeHeight: number
  center: number
  top: number
  width: number
}>
type RetryLabelCandidate = Readonly<{ side: RetryLabelSide; align: RetryLabelAlign; extraLanes: number }>

export const RETRY_LABEL_HEIGHT = 22
export const RETRY_LABEL_BASE_OFFSET = 8
export const RETRY_LABEL_LANE_GAP = 6
const DEFAULT_NODE_WIDTH = 300
const DEFAULT_NODE_HEIGHT = 120
/** Prefer a nearby top or side placement over stacking the label several rows up. */
const LABEL_CANDIDATES: readonly RetryLabelCandidate[] = [
  { side: 'top', align: 'center', extraLanes: 0 },
  { side: 'top', align: 'start', extraLanes: 0 },
  { side: 'top', align: 'end', extraLanes: 0 },
  { side: 'left', align: 'start', extraLanes: 0 },
  { side: 'right', align: 'start', extraLanes: 0 },
  { side: 'top', align: 'center', extraLanes: 1 },
]

function retryStateLabelText(state: RetryPreviewCanvasState): string {
  switch (state) {
    case 'origin':
      return 'Retry origin'
    case 'will-retry':
      return 'In retry scope'
    case 'retained':
      return 'Retains prior result'
    case 'not-retried':
      return 'Not retried — remains failed'
  }
}

function overlaps(left: RetryLabelBounds, right: RetryLabelBounds): boolean {
  return left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top
}

function getAbsolutePosition(
  node: RetryPreviewLayoutNode,
  nodesById: ReadonlyMap<string, RetryPreviewLayoutNode>,
  cache: Map<string, { x: number; y: number }>,
  visited = new Set<string>()
): { x: number; y: number } {
  const knownPosition = cache.get(node.id)
  if (knownPosition) return knownPosition
  if (!node.parentId || visited.has(node.parentId)) return node.position

  const parent = nodesById.get(node.parentId)
  if (!parent) return node.position

  visited.add(node.id)
  const parentPosition = getAbsolutePosition(parent, nodesById, cache, visited)
  const position = { x: parentPosition.x + node.position.x, y: parentPosition.y + node.position.y }
  cache.set(node.id, position)
  return position
}

function getSideAlignedTop(entry: RetryLabelEntry, align: RetryLabelAlign): number {
  if (align === 'end') return entry.top + entry.nodeHeight - RETRY_LABEL_HEIGHT
  if (align === 'center') return entry.top + entry.nodeHeight / 2 - RETRY_LABEL_HEIGHT / 2
  return entry.top
}

function getTopAlignedLeft(entry: RetryLabelEntry, align: RetryLabelAlign): number {
  if (align === 'start') return entry.nodeLeft
  if (align === 'end') return entry.nodeLeft + entry.nodeWidth - entry.width
  return entry.center - entry.width / 2
}

function getLabelBounds(
  entry: RetryLabelEntry,
  side: RetryLabelSide,
  align: RetryLabelAlign,
  offset: number
): RetryLabelBounds {
  if (side === 'left' || side === 'right') {
    const top = getSideAlignedTop(entry, align)
    const left = side === 'left' ? entry.nodeLeft - offset - entry.width : entry.nodeLeft + entry.nodeWidth + offset
    return { left, right: left + entry.width, top, bottom: top + RETRY_LABEL_HEIGHT }
  }

  const left = getTopAlignedLeft(entry, align)
  const bottom = entry.top - offset
  return {
    left,
    right: left + entry.width,
    top: bottom - RETRY_LABEL_HEIGHT,
    bottom,
  }
}

function collides(
  bounds: RetryLabelBounds,
  nodeId: string,
  nodeBounds: ReadonlyArray<RetryLabelBounds & { id: string }>,
  placedLabels: readonly RetryLabelBounds[]
): boolean {
  return (
    nodeBounds.some((node) => node.id !== nodeId && overlaps(bounds, node)) ||
    placedLabels.some((placed) => overlaps(bounds, placed))
  )
}

function candidateOffset(extraLanes: number): number {
  return RETRY_LABEL_BASE_OFFSET + extraLanes * (RETRY_LABEL_HEIGHT + RETRY_LABEL_LANE_GAP)
}

/** Place retry labels next to their nodes, trying left/right before moving them far up. */
export function getRetryPreviewLabelPlacements(
  nodes: readonly RetryPreviewLayoutNode[],
  states: ReadonlyMap<string, RetryPreviewCanvasState>,
  zoom: number
): Map<string, RetryLabelPlacement> {
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  const absolutePositionById = new Map<string, { x: number; y: number }>()

  const nodeBounds = nodes.map((node) => {
    const position = getAbsolutePosition(node, nodesById, absolutePositionById)
    const width = node.measured?.width ?? node.width ?? DEFAULT_NODE_WIDTH
    const height = node.measured?.height ?? node.height ?? DEFAULT_NODE_HEIGHT
    const left = position.x * zoom
    const top = position.y * zoom
    return { id: node.id, left, right: left + width * zoom, top, bottom: top + height * zoom }
  })
  const labelEntries = [...states]
    .map(([nodeId, state]) => {
      const node = nodesById.get(nodeId)
      if (!node) return undefined
      const position = getAbsolutePosition(node, nodesById, absolutePositionById)
      const width = node.measured?.width ?? node.width ?? DEFAULT_NODE_WIDTH
      const height = node.measured?.height ?? node.height ?? DEFAULT_NODE_HEIGHT
      const nodeLeft = position.x * zoom
      const nodeWidth = width * zoom
      return {
        nodeId,
        nodeLeft,
        nodeWidth,
        nodeHeight: height * zoom,
        center: nodeLeft + nodeWidth / 2,
        top: position.y * zoom,
        width: retryStateLabelText(state).length * 7 + 20,
      }
    })
    .filter((entry): entry is RetryLabelEntry => entry !== undefined)
    .sort((left, right) => left.top - right.top || left.center - right.center)

  const placements = new Map<string, RetryLabelPlacement>()
  const placedLabels: RetryLabelBounds[] = []

  for (const entry of labelEntries) {
    let chosen: { placement: RetryLabelPlacement; bounds: RetryLabelBounds } | undefined
    for (const candidate of LABEL_CANDIDATES) {
      const offset = candidateOffset(candidate.extraLanes)
      const bounds = getLabelBounds(entry, candidate.side, candidate.align, offset)
      if (collides(bounds, entry.nodeId, nodeBounds, placedLabels)) continue
      chosen = { placement: { offset, align: candidate.align, side: candidate.side }, bounds }
      break
    }

    const fallback = {
      placement: { offset: RETRY_LABEL_BASE_OFFSET, align: 'start' as const, side: 'left' as const },
      bounds: getLabelBounds(entry, 'left', 'start', RETRY_LABEL_BASE_OFFSET),
    }
    const selected = chosen ?? fallback
    placements.set(entry.nodeId, selected.placement)
    placedLabels.push(selected.bounds)
  }

  return placements
}
