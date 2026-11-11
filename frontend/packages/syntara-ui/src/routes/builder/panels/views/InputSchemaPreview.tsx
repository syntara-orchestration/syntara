import { Content, ContentVariants, Label } from '@patternfly/react-core'
import { TreeView, type TreeViewDataItem } from '@patternfly/react-core'
import { RhUiInformationIcon } from '@patternfly/react-icons'
import type { OutputFieldDef } from '@syntara/contracts'
import { useCallback, useMemo } from 'react'

import { buildExpression, canvasNodeIdForExpression } from '../../../../utils/expressions/templateBuilder'
import { highlightText } from '../../../../utils/highlightText'
import { CopyExpressionAction, DraggableTreeLeaf } from '../components/DraggableTreeLeaf'
import { DRAG_TYPE_FIELD, type FieldDragData } from '../utils/dragTypes'
import { toTreeItemId } from '../utils/treeHelpers'
import { getTypeLabel } from '../utils/typeLabels'

import styles from './InputSchemaPreview.module.css'

export type InputSchemaPreviewProps = {
  fields?: OutputFieldDef[]
  tree?: InputSchemaPreviewNode[]
  nodeId: string
  searchTerm?: string
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
  searchTerm?: string
}

function PreviewField({ name, type, description, nodeId, fieldPath, searchTerm }: Readonly<PreviewFieldProps>) {
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

  const label = `${typeLabel} ${name}`
  return (
    <DraggableTreeLeaf
      label={searchTerm ? highlightText(label, searchTerm) : label}
      secondaryText={searchTerm ? highlightText(description, searchTerm) : description}
      onDragStart={handleDragStart}
    />
  )
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

/**
 * Filter tree nodes based on search term, keeping ancestor groups visible when descendants match.
 * Returns null if node and all descendants don't match the search.
 */
function filterTreeNode(node: InputSchemaPreviewNode, searchTerm: string): InputSchemaPreviewNode | null {
  const lowerSearch = searchTerm.toLowerCase()
  const nameMatches = node.name.toLowerCase().includes(lowerSearch)
  const descriptionMatches = node.description?.toLowerCase().includes(lowerSearch) ?? false

  // If this is a leaf node, return it only if it matches
  if (!node.children || node.children.length === 0) {
    return nameMatches || descriptionMatches ? node : null
  }

  // For group nodes, recursively filter children
  const filteredChildren = node.children.map((child) => filterTreeNode(child, searchTerm)).filter(Boolean)

  // Keep this group if it matches or has any matching descendants
  if (nameMatches || descriptionMatches || filteredChildren.length > 0) {
    return {
      ...node,
      children: filteredChildren as InputSchemaPreviewNode[],
    }
  }

  return null
}

/**
 * Filter tree nodes array based on search term.
 */
function filterTree(nodes: InputSchemaPreviewNode[], searchTerm: string): InputSchemaPreviewNode[] {
  if (!searchTerm.trim()) return nodes
  return nodes.map((node) => filterTreeNode(node, searchTerm)).filter(Boolean) as InputSchemaPreviewNode[]
}

function buildTreeData(nodes: InputSchemaPreviewNode[], nodeId: string, searchTerm?: string): TreeViewDataItem[] {
  return nodes.map((node) => {
    const id = toTreeItemId([nodeId, ...node.fieldPath])
    const hasChildren = Boolean(node.children?.length)
    if (node.isGroup || hasChildren) {
      const groupLabel = `${getTypeLabel(node.type)} ${node.name}`
      return {
        id,
        name: (
          <Label isCompact color="grey">
            {searchTerm ? highlightText(groupLabel, searchTerm) : groupLabel}
          </Label>
        ),
        defaultExpanded: true,
        hasBadge: false,
        children: buildTreeData(node.children ?? [], nodeId, searchTerm),
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
          searchTerm={searchTerm}
        />
      ),
      action: <CopyExpressionAction expressionText={expression} />,
      hasBadge: false,
    }
  })
}

export function InputSchemaPreview({ fields = [], tree, nodeId, searchTerm }: Readonly<InputSchemaPreviewProps>) {
  const expressionNodeId = canvasNodeIdForExpression(nodeId)
  const treeNodes = tree ?? fields.map((field) => toInputSchemaPreviewNode(field))
  const filteredNodes = useMemo(
    () => (searchTerm ? filterTree(treeNodes, searchTerm) : treeNodes),
    [treeNodes, searchTerm]
  )
  const treeData: TreeViewDataItem[] = useMemo(
    () => buildTreeData(filteredNodes, expressionNodeId, searchTerm),
    [filteredNodes, expressionNodeId, searchTerm]
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
