import { ActionList, ActionListItem, Button } from '@patternfly/react-core'
import { RhUiAddSquareIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { EdgeLabelRenderer } from '@xyflow/react'
import React from 'react'

import { useIsStepFormReadOnly } from '../VersionViewContext'

type EdgeActionsProps = {
  /** X coordinate for positioning the actions */
  labelX: number
  /** Y coordinate for positioning the actions */
  labelY: number
  /** Callback when button area is entered - keeps edge visible */
  onButtonMouseEnter: () => void
  /** Callback when button area is left - allows edge to hide after delay */
  onButtonMouseLeave: () => void
  /** Handler for adding a node */
  onAddNode: (event: React.MouseEvent) => void
  /** Handler for deleting the edge */
  onDelete: (event: React.MouseEvent) => void
}

/**
 * Shared edge action buttons component
 * Displays Add and Delete buttons in an ActionList when edge is hovered or active
 */
export function EdgeActions(props: EdgeActionsProps) {
  const { labelX, labelY, onButtonMouseEnter, onButtonMouseLeave, onAddNode, onDelete } = props
  const isReadOnly = useIsStepFormReadOnly()

  if (isReadOnly) return null

  return (
    <EdgeLabelRenderer>
      {/* Outer div helps position and keep actions up after hovering edge */}
      <div
        role="toolbar"
        aria-label="Edge actions"
        style={{
          position: 'absolute',
          transform: `translate(-50%, -120%) translate(${labelX}px,${labelY}px)`,
          pointerEvents: 'all',
          zIndex: 1000,
        }}
        className="nodrag nopan"
        onMouseEnter={onButtonMouseEnter}
        onMouseLeave={onButtonMouseLeave}
      >
        <ActionList isIconList>
          <ActionListItem>
            <Button variant="control" onClick={onAddNode} title="Add step">
              <RhUiAddSquareIcon />
            </Button>
          </ActionListItem>
          <ActionListItem>
            <Button variant="control" onClick={onDelete} title="Delete edge">
              <RhUiTrashIcon />
            </Button>
          </ActionListItem>
        </ActionList>
      </div>
    </EdgeLabelRenderer>
  )
}
