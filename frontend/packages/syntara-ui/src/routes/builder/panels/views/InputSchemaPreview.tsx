import { Content, ContentVariants, EmptyState, EmptyStateBody, Flex, FlexItem } from '@patternfly/react-core'
import { TreeView, type TreeViewDataItem } from '@patternfly/react-core'
import type { OutputFieldDef } from '@syntara/contracts'
import { useCallback, useMemo } from 'react'

import { FormLabelWithHelp } from '../../../../components/FormLabelWithHelp'
import { SynLabel } from '../../../../components/labels/SynLabel'
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
  runtimeValues?: Record<string, unknown>
  helpText?: string
}

export type InputSchemaPreviewNode = {
  name: string
  type: OutputFieldDef['type']
  description?: string
  fieldPath: string[]
  children?: InputSchemaPreviewNode[]
  isGroup?: boolean
  required?: boolean
}

type PreviewFieldProps = {
  name: string
  type: OutputFieldDef['type']
  description: string
  nodeId: string
  fieldPath: string[]
  required?: boolean
  searchTerm?: string
  runtimeValue?: unknown
  hasRuntimeValue: boolean
}

function PreviewField({
  name,
  type,
  description,
  nodeId,
  fieldPath,
  required,
  searchTerm,
  runtimeValue,
  hasRuntimeValue,
}: Readonly<PreviewFieldProps>) {
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

  const requiredBadge = required ? <SynLabel color="blue">Required</SynLabel> : null

  const fieldLabel = `${typeLabel} ${name}`
  const label = (
    <Flex className={styles.fieldLabel} alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
      <FlexItem>
        <Content component={ContentVariants.small}>
          {searchTerm ? highlightText(fieldLabel, searchTerm) : fieldLabel}
        </Content>
      </FlexItem>
      {requiredBadge && <FlexItem>{requiredBadge}</FlexItem>}
    </Flex>
  )
  const runtimeText = hasRuntimeValue ? formatRuntimeValue(runtimeValue) : undefined
  const hasDetails = Boolean(description.trim()) || hasRuntimeValue
  const secondaryText = hasDetails ? (
    <span className={styles.fieldDetails}>
      {description.trim() && (
        <span className={styles.fieldDescription}>
          {searchTerm ? highlightText(description, searchTerm) : description}
        </span>
      )}
      {runtimeText !== undefined && <span className={styles.runtimeValue}>{runtimeText}</span>}
    </span>
  ) : undefined

  return <DraggableTreeLeaf label={label} secondaryText={secondaryText} onDragStart={handleDragStart} />
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function formatRuntimeValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null) return 'null'
  return JSON.stringify(value) ?? ''
}

function getRuntimeValueAtPath(
  runtimeValues: Record<string, unknown> | undefined,
  fieldPath: string[]
): { found: boolean; value?: unknown } {
  let current: unknown = runtimeValues

  for (const segment of fieldPath) {
    if (Array.isArray(current)) {
      const index = Number(segment)
      if (!Number.isInteger(index) || index < 0 || index >= current.length) return { found: false }
      current = current[index]
      continue
    }
    if (!isRecord(current) || !Object.prototype.hasOwnProperty.call(current, segment)) return { found: false }
    current = current[segment]
  }

  return current === undefined ? { found: false } : { found: true, value: current }
}

function toInputSchemaPreviewNode(field: OutputFieldDef, parentPath: string[] = []): InputSchemaPreviewNode {
  return {
    name: field.name,
    type: field.type,
    description: field.description,
    fieldPath: [...parentPath, field.name],
    ...('required' in field && typeof field.required === 'boolean' ? { required: field.required } : {}),
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
  const fullPath = node.fieldPath.join('.').toLowerCase()
  const publicOutputPath = (node.fieldPath[0] === 'outputs' ? node.fieldPath.slice(1) : node.fieldPath)
    .join('.')
    .toLowerCase()
  const pathMatches = fullPath.includes(lowerSearch) || publicOutputPath.includes(lowerSearch)

  // If this is a leaf node, return it only if it matches
  if (!node.children || node.children.length === 0) {
    return nameMatches || descriptionMatches || pathMatches ? node : null
  }

  // For group nodes, recursively filter children
  const filteredChildren = node.children.map((child) => filterTreeNode(child, searchTerm)).filter(Boolean)

  // Keep this group if it matches or has any matching descendants
  if (nameMatches || descriptionMatches || pathMatches || filteredChildren.length > 0) {
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

function buildTreeData(
  nodes: InputSchemaPreviewNode[],
  nodeId: string,
  searchTerm?: string,
  runtimeValues?: Record<string, unknown>
): TreeViewDataItem[] {
  return nodes.map((node) => {
    const id = toTreeItemId([nodeId, ...node.fieldPath])
    const hasChildren = Boolean(node.children?.length)
    if (node.isGroup || hasChildren) {
      const groupLabel = `${getTypeLabel(node.type)} ${node.name}`
      const runtime = getRuntimeValueAtPath(runtimeValues, node.fieldPath)
      const runtimeText = runtime.found ? formatRuntimeValue(runtime.value) : undefined
      const isSyntheticOutputsGroup = node.fieldPath.length === 1 && node.name === 'outputs'
      // Collapse public output groups until authors expand them; searches reveal matching ancestors.
      const isNestedOutputGroup = node.fieldPath.length >= 2 && node.fieldPath[node.fieldPath.length - 2] === 'outputs'
      const defaultExpanded = Boolean(searchTerm?.trim()) || !isNestedOutputGroup

      return {
        id,
        name: (
          <span className={styles.groupDetails}>
            <span className={styles.groupLabel}>
              <SynLabel color="grey">{searchTerm ? highlightText(groupLabel, searchTerm) : groupLabel}</SynLabel>
              {node.required && <SynLabel color="blue">Required</SynLabel>}
            </span>
            {node.description?.trim() && (
              <span className={styles.fieldDescription}>
                {searchTerm ? highlightText(node.description, searchTerm) : node.description}
              </span>
            )}
            {!isSyntheticOutputsGroup && runtimeText !== undefined && (
              <span className={styles.runtimeValue}>{runtimeText}</span>
            )}
          </span>
        ),
        defaultExpanded,
        hasBadge: false,
        children: buildTreeData(node.children ?? [], nodeId, searchTerm, runtimeValues),
      }
    }

    const expression = buildExpression({ nodeId, fieldPath: node.fieldPath })
    const runtime = getRuntimeValueAtPath(runtimeValues, node.fieldPath)
    return {
      id,
      name: (
        <PreviewField
          name={node.name}
          type={node.type}
          description={node.description ?? ''}
          nodeId={nodeId}
          fieldPath={node.fieldPath}
          required={node.required}
          searchTerm={searchTerm}
          runtimeValue={runtime.value}
          hasRuntimeValue={runtime.found}
        />
      ),
      action: <CopyExpressionAction expressionText={expression} />,
      hasBadge: false,
    }
  })
}

export function InputSchemaPreview({
  fields = [],
  tree,
  nodeId,
  searchTerm,
  runtimeValues,
  helpText = 'Run the step to see actual values.',
}: Readonly<InputSchemaPreviewProps>) {
  const expressionNodeId = canvasNodeIdForExpression(nodeId)
  const treeNodes = tree ?? fields.map((field) => toInputSchemaPreviewNode(field))
  const normalizedSearchTerm = searchTerm?.trim() ?? ''
  const filteredNodes = useMemo(
    () => (normalizedSearchTerm ? filterTree(treeNodes, normalizedSearchTerm) : treeNodes),
    [treeNodes, normalizedSearchTerm]
  )
  const treeData: TreeViewDataItem[] = useMemo(
    () => buildTreeData(filteredNodes, expressionNodeId, normalizedSearchTerm, runtimeValues),
    [filteredNodes, expressionNodeId, normalizedSearchTerm, runtimeValues]
  )

  if (treeData.length === 0) {
    if (normalizedSearchTerm) {
      return (
        <EmptyState headingLevel="h4" titleText="No output fields match your search" variant="xs">
          <EmptyStateBody>No output fields match “{normalizedSearchTerm}”.</EmptyStateBody>
        </EmptyState>
      )
    }
    return null
  }

  return (
    <div className={styles.previewContainer}>
      <Content component={ContentVariants.small} className={styles.previewHeader}>
        <FormLabelWithHelp label="Expected output fields" helpText={helpText} />
      </Content>
      <TreeView key={normalizedSearchTerm || 'unfiltered'} data={treeData} aria-label="Schema preview" />
    </div>
  )
}
