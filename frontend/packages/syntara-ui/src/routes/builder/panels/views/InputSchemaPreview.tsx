import { Content, ContentVariants } from '@patternfly/react-core'
import { TreeView, type TreeViewDataItem } from '@patternfly/react-core'
import { RhUiInformationIcon } from '@patternfly/react-icons'
import { useCallback, useMemo } from 'react'

import { buildExpression, canvasNodeIdForExpression } from '../../../../utils/expressions/templateBuilder'
import { CopyExpressionAction, DraggableTreeLeaf } from '../components/DraggableTreeLeaf'
import { DRAG_TYPE_FIELD, type FieldDragData } from '../utils/dragTypes'
import type { PreviewFieldDef } from '../utils/effectiveOutputSchema'
import { getTypeLabel } from '../utils/typeLabels'

import styles from './InputSchemaPreview.module.css'

export type InputSchemaPreviewProps = {
  fields: PreviewFieldDef[]
  nodeId: string
}

type PreviewFieldProps = {
  field: PreviewFieldDef
  nodeId: string
  fieldPath: string[]
}

function PreviewField({ field, nodeId, fieldPath }: Readonly<PreviewFieldProps>) {
  const typeLabel = getTypeLabel(field.type)
  const expression = useMemo(() => buildExpression({ nodeId, fieldPath }), [nodeId, fieldPath])
  const secondaryText = [field.displayName !== field.name ? field.displayName : undefined, field.description]
    .filter(Boolean)
    .join(' — ')

  const handleDragStart = useCallback(
    (e: React.DragEvent) => {
      const data: FieldDragData = {
        type: DRAG_TYPE_FIELD,
        nodeId,
        fieldPath,
      }
      e.dataTransfer.setData('application/json', JSON.stringify(data))
      e.dataTransfer.setData('text/plain', expression)
      e.dataTransfer.effectAllowed = 'copy'
    },
    [nodeId, fieldPath, expression]
  )

  return (
    <DraggableTreeLeaf
      label={`${typeLabel} ${field.name}`}
      secondaryText={secondaryText || undefined}
      onDragStart={handleDragStart}
    />
  )
}

function treeItemId(nodeId: string, fieldPath: string[]): string {
  return `schema-${encodeURIComponent(JSON.stringify([nodeId, ...fieldPath]))}`
}

function buildTreeItem(field: PreviewFieldDef, nodeId: string, parentPath: string[] = []): TreeViewDataItem {
  const fieldPath = [...parentPath, field.name]
  const children = field.children?.map((child) => buildTreeItem(child, nodeId, fieldPath))

  return {
    id: treeItemId(nodeId, fieldPath),
    name: <PreviewField field={field} nodeId={nodeId} fieldPath={fieldPath} />,
    action: <CopyExpressionAction expressionText={buildExpression({ nodeId, fieldPath })} />,
    ...(children && children.length > 0 ? { children, defaultExpanded: true } : {}),
    hasBadge: false,
  }
}

export function InputSchemaPreview({ fields, nodeId }: Readonly<InputSchemaPreviewProps>) {
  const expressionNodeId = canvasNodeIdForExpression(nodeId)
  const treeData: TreeViewDataItem[] = useMemo(
    () => fields.map((field) => buildTreeItem(field, expressionNodeId)),
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
