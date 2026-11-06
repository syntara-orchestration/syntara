import { Content, ContentVariants, Label } from '@patternfly/react-core'
import { TreeView, type TreeViewDataItem } from '@patternfly/react-core'
import { RhUiInformationIcon } from '@patternfly/react-icons'
import type { OutputFieldDef } from '@syntara/contracts'
import { useCallback, useMemo } from 'react'

import { buildExpression, canvasNodeIdForExpression } from '../../../../utils/expressions/templateBuilder'
import { CopyExpressionAction, DraggableTreeLeaf } from '../components/DraggableTreeLeaf'
import { DRAG_TYPE_FIELD, type FieldDragData } from '../utils/dragTypes'
import { toTreeItemId } from '../utils/treeHelpers'
import { getTypeLabel } from '../utils/typeLabels'

import styles from './InputSchemaPreview.module.css'

export type InputSchemaPreviewProps = {
  fields?: OutputFieldDef[]
  tree?: InputSchemaPreviewNode[]
  nodeId: string
}

export type InputSchemaPreviewNode = {
  name: string
  type: OutputFieldDef['type']
  description?: string
  fieldPath: string[]
  children?: InputSchemaPreviewNode[]
  isGroup?: boolean
}

type PreviewFieldProps = {
  name: string
  type: OutputFieldDef['type']
  description: string
  nodeId: string
  fieldPath: string[]
}

function PreviewField({ name, type, description, nodeId, fieldPath }: Readonly<PreviewFieldProps>) {
  const typeLabel = getTypeLabel(type)
  const expression = useMemo(() => buildExpression({ nodeId, fieldPath }), [nodeId, fieldPath])

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

  return <DraggableTreeLeaf label={`${typeLabel} ${name}`} secondaryText={description} onDragStart={handleDragStart} />
}

function toInputSchemaPreviewNode(field: OutputFieldDef, parentPath: string[] = []): InputSchemaPreviewNode {
  return {
    name: field.name,
    type: field.type,
    description: field.description,
    fieldPath: [...parentPath, field.name],
    ...(field.children && field.children.length > 0
      ? {
          children: field.children.map((child) => toInputSchemaPreviewNode(child, [...parentPath, field.name])),
          isGroup: true,
        }
      : {}),
  }
}

function buildTreeData(nodes: InputSchemaPreviewNode[], nodeId: string): TreeViewDataItem[] {
  return nodes.map((node) => {
    const id = toTreeItemId([nodeId, ...node.fieldPath])
    const hasChildren = Boolean(node.children?.length)
    if (node.isGroup || hasChildren) {
      return {
        id,
        name: (
          <Label isCompact color="grey">
            {getTypeLabel(node.type)} {node.name}
          </Label>
        ),
        defaultExpanded: true,
        hasBadge: false,
        children: buildTreeData(node.children ?? [], nodeId),
      }
    }

    const expression = buildExpression({ nodeId, fieldPath: node.fieldPath })
    return {
      id,
      name: (
        <PreviewField
          name={node.name}
          type={node.type}
          description={node.description ?? ''}
          nodeId={nodeId}
          fieldPath={node.fieldPath}
        />
      ),
      action: <CopyExpressionAction expressionText={expression} />,
      hasBadge: false,
    }
  })
}

export function InputSchemaPreview({ fields = [], tree, nodeId }: Readonly<InputSchemaPreviewProps>) {
  const expressionNodeId = canvasNodeIdForExpression(nodeId)
  const treeNodes = tree ?? fields.map((field) => toInputSchemaPreviewNode(field))
  const treeData: TreeViewDataItem[] = useMemo(
    () => buildTreeData(treeNodes, expressionNodeId),
    [treeNodes, expressionNodeId]
  )

  if (treeData.length === 0) {
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
