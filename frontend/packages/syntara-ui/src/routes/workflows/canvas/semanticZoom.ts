/**
 * When the workflow canvas viewport zoom is at or below this scale, nodes render as
 * icon-only tiles (similar to PatternFly Topology semantic zoom); name and type show in a tooltip.
 */
export const SEMANTIC_ZOOM_MAX_SCALE = 0.5

/** Square icon tile width/height in flow coordinates when semantic zoom is active. */
export const SEMANTIC_ZOOM_TILE_SIZE_PX = 224

/** Vertical center of connection handles on the tile (not the label panel). */
export const SEMANTIC_ZOOM_TILE_HANDLE_TOP_PX = SEMANTIC_ZOOM_TILE_SIZE_PX / 2

/**
 * Primary tooltip/canvas line for semantic zoom: non-empty trimmed `name`, or `whenEmpty`.
 * Use with a stable fallback such as `Untitled ${metadata.label}` so all activity nodes stay consistent.
 */
export function semanticZoomActivityTitle(name: string | undefined | null, whenEmpty: string): string {
  const trimmed = name?.trim()
  return trimmed ? trimmed : whenEmpty
}
