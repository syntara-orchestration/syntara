import { Button, Label, TreeView, type TreeViewDataItem } from '@patternfly/react-core'
import { RhUiExternalLinkIcon } from '@patternfly/react-icons'
import { useMemo } from 'react'

import styles from '../panels.module.css'
import { formatLeafValue, isExpandable, isUrlValue, toTreeItemId } from '../utils/treeHelpers'
import { getTypeLabelFromValue } from '../utils/typeLabels'

export type OutputSchemaViewProps = {
  data: Record<string, unknown> | null
}

function buildReadOnlyTreeData(data: Record<string, unknown>, parentPath: string[] = []): TreeViewDataItem[] {
  return Object.entries(data).map(([key, value]) => {
    const currentPath = [...parentPath, key]
    const typeLabel = getTypeLabelFromValue(value)

    if (isExpandable(value)) {
      return {
        id: toTreeItemId(currentPath),
        name: (
          <Label isCompact color="grey">
            {typeLabel} {key}
          </Label>
        ),
        defaultExpanded: true,
        children: buildReadOnlyTreeData(value, currentPath),
      }
    }

    const formatted = formatLeafValue(value)

    return {
      id: toTreeItemId(currentPath),
      name: (
        // eslint-disable-next-line syntara/prefer-pf-text-components, no-restricted-syntax -- span provides aria-label for tree node accessibility; PF6 has no inline text component; aria-label needed here for screen readers to announce the full tree node content
        <span aria-label={`${key}: ${formatted}, type ${typeLabel}`}>
          <Label isCompact color="grey">
            {typeLabel}
          </Label>{' '}
          {key}: <span className={styles.leafValue}>{formatted}</span>
        </span>
      ),
      ...(isUrlValue(value) && {
        action: (
          <Button
            variant="plain"
            component="a"
            href={value}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open ${key} in new tab`}
            size="sm"
          >
            <RhUiExternalLinkIcon />
          </Button>
        ),
      }),
    }
  })
}

export function OutputSchemaView({ data }: Readonly<OutputSchemaViewProps>) {
  const treeData = useMemo(() => {
    if (!data) return []
    return buildReadOnlyTreeData(data)
  }, [data])

  if (!data) {
    return null
  }

  return <TreeView data={treeData} aria-label="Output schema" />
}
