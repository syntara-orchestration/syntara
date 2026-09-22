import { permissionTooltip } from '../../../../hooks/permissionUtils'
import type { NodeKind } from '../../../../hooks/useNodeKindsQuery'

/** Flow control kinds keep the engine running, so they can never be switched off. */
export const NOT_SWITCHABLE_TOOLTIP = 'This node kind is required by the workflow engine and cannot be switched off.'

/**
 * Explain why a node kind's kill switch is inert, or `null` when it is usable.
 *
 * @param nodeKind Registry entry for the row.
 * @param canWrite Whether the caller holds `setting:write`.
 */
export function nodeKindSwitchTooltip(nodeKind: NodeKind, canWrite: boolean): string | null {
  if (!nodeKind.switchable) return NOT_SWITCHABLE_TOOLTIP
  if (!canWrite) return permissionTooltip('enable or disable node kinds', 'setting:write')
  return null
}
