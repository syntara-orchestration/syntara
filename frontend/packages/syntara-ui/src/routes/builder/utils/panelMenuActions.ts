import type { Node } from '@xyflow/react'

import type { useStepMenuActions } from '../../workflows/canvas/nodes/hooks/useStepMenuActions'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

type MenuActions = ReturnType<typeof useStepMenuActions>

export function buildPanelMenuActions(
  mode: 'add' | 'edit',
  node: Node<NodeType['data']> | undefined,
  menuActions: MenuActions,
  onClose: () => void
) {
  if (mode !== 'edit' || !node) return []

  return menuActions
    .filter((action) => action.id !== 'view-details')
    .map((action) => {
      if (action.separator || action.id !== 'delete') {
        return action
      }
      return {
        ...action,
        onClick: () => {
          action.onClick()
          onClose()
        },
      }
    })
}
