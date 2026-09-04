type FlowNodeSnapshot = {
  id: string
  position?: { x: number; y: number }
  measured?: { height?: number }
}

export type LoopBackEdgeGeometry = {
  source?: { x: number; y: number; height: number }
  target?: { x: number; y: number; height: number }
  loopBodyMaxBottom: number
}

function getNodeBottom(node: { position: { y: number }; measured?: { height?: number } }): number {
  return node.position.y + (node.measured?.height ?? 0)
}

/**
 * Selects only the node geometry LoopBackEdge needs for path routing.
 * Keeps subscriptions narrow so unrelated node updates do not re-render the edge.
 */
export function selectLoopBackEdgeGeometry(
  nodes: FlowNodeSnapshot[],
  source: string,
  target: string,
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number
): LoopBackEdgeGeometry {
  const targetNode = nodes.find((n) => n.id === target)
  const sourceNode = nodes.find((n) => n.id === source)

  let loopBodyMaxBottom = sourceY

  if (targetNode?.position) {
    loopBodyMaxBottom = Math.max(loopBodyMaxBottom, getNodeBottom(targetNode as { position: { y: number }; measured?: { height?: number } }))
  }
  if (sourceNode?.position) {
    loopBodyMaxBottom = Math.max(loopBodyMaxBottom, getNodeBottom(sourceNode as { position: { y: number }; measured?: { height?: number } }))
  }

  if (targetNode && sourceNode) {
    nodes.forEach((node) => {
      if (!node.position || node.measured?.height == null) return
      if (node.id === source || node.id === target) return
      const nodeY = node.position.y + node.measured.height / 2
      const nodeX = node.position.x
      if (
        Math.abs(nodeY - targetY) < 100 &&
        nodeX > targetX &&
        nodeX < sourceX
      ) {
        loopBodyMaxBottom = Math.max(
          loopBodyMaxBottom,
          getNodeBottom(node as { position: { y: number }; measured?: { height?: number } })
        )
      }
    })
  }

  return {
    source: sourceNode?.position
      ? { x: sourceNode.position.x, y: sourceNode.position.y, height: sourceNode.measured?.height ?? 0 }
      : undefined,
    target: targetNode?.position
      ? { x: targetNode.position.x, y: targetNode.position.y, height: targetNode.measured?.height ?? 0 }
      : undefined,
    loopBodyMaxBottom,
  }
}

export function loopBackEdgeGeometryEqual(a: LoopBackEdgeGeometry, b: LoopBackEdgeGeometry): boolean {
  if (a.loopBodyMaxBottom !== b.loopBodyMaxBottom) return false
  if (!!a.source !== !!b.source || !!a.target !== !!b.target) return false
  if (a.source && b.source) {
    if (a.source.x !== b.source.x || a.source.y !== b.source.y || a.source.height !== b.source.height) return false
  }
  if (a.target && b.target) {
    if (a.target.x !== b.target.x || a.target.y !== b.target.y || a.target.height !== b.target.height) return false
  }
  return true
}
