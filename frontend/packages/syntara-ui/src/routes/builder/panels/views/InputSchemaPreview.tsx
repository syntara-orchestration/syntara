import { Content, ContentVariants } from '@patternfly/react-core'
import { TreeView, type TreeViewDataItem } from '@patternfly/react-core'
import { RhUiInformationIcon } from '@patternfly/react-icons'
import type { OutputFieldDef } from '@syntara/contracts'
import { useCallback, useMemo } from 'react'

import { buildExpression, canvasNodeIdForExpression } from '../../../../utils/expressions/templateBuilder'
import { CopyExpressionAction, DraggableTreeLeaf } from '../components/DraggableTreeLeaf'
import { DRAG_TYPE_FIELD, type FieldDragData } from '../utils/dragTypes'
import { getTypeLabel } from '../utils/typeLabels'

import styles from './InputSchemaPreview.module.css'

export type InputSchemaPreviewProps = {
  fields: OutputFieldDef[]
  nodeId: string
}

type PreviewFieldProps = {
  field: OutputFieldDef
  nodeId: string
}

function PreviewField({ field, nodeId }: Readonly<PreviewFieldProps>) {
  const typeLabel = getTypeLabel(field.type)
  const expression = useMemo(() => buildExpression({ nodeId, fieldPath: [field.name] }), [nodeId, field.name])

  const handleDragStart = useCallback(
    (e: React.DragEvent) => {
      const data: FieldDragData = {
        type: DRAG_TYPE_FIELD,
        nodeId,
        fieldPath: [field.name],
      }
      e.dataTransfer.setData('application/json', JSON.stringify(data))
      e.dataTransfer.setData('text/plain', expression)
      e.dataTransfer.effectAllowed = 'copy'
    },
    [nodeId, field.name, expression]
  )

  return (
    <DraggableTreeLeaf
      label={`${typeLabel} ${field.name}`}
      secondaryText={field.description}
      onDragStart={handleDragStart}
    />
  )
}

export function InputSchemaPreview({ fields, nodeId }: Readonly<InputSchemaPreviewProps>) {
  const expressionNodeId = canvasNodeIdForExpression(nodeId)
  const treeData: TreeViewDataItem[] = useMemo(
    () =>
      fields.map((field) => ({
        id: field.name,
        name: <PreviewField field={field} nodeId={expressionNodeId} />,
        action: (
          <CopyExpressionAction
            expressionText={buildExpression({ nodeId: expressionNodeId, fieldPath: [field.name] })}
          />
        ),
        hasBadge: false,
      })),
    [fields, expressionNodeId]
  )

  if (fields.length === 0) {
    return null
  }

  return (
    <div className={styles.previewContainer}>
      <Content component={ContentVariants.small} className={styles.previewHeader}>
        <RhUiInformationIcon /> Expected output fields (run step to see actual values)
      </Content>
      <TreeView data={treeData} aria-label="Schema preview" />
    </div>
  )
}
