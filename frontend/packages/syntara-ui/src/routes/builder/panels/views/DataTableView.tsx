import { Thead, Tr, Th, Tbody, Td } from '@patternfly/react-table'
import { type ReactNode, useCallback, useMemo } from 'react'

import { NxPanelContentStack } from '../../../../components/layout/NxPanelContentStack'
import { NxScrollableTableContainer } from '../../../../components/table/NxScrollableTableContainer'
import { buildRowKey, toSafeString } from '../utils/tableHelpers'

export type DataTableViewProps = {
  data: Record<string, unknown> | Record<string, unknown>[] | null
  ariaLabel: string
  renderCell?: (text: string) => ReactNode
  renderHeader?: (text: string) => ReactNode
}

export function DataTableView({ data, ariaLabel, renderCell, renderHeader }: Readonly<DataTableViewProps>) {
  const { columns, rows } = useMemo(() => {
    if (!data) return { columns: [] as string[], rows: [] as Record<string, unknown>[] }

    const rowArray = Array.isArray(data) ? data : [data]
    const columnSet = new Set<string>()
    for (const row of rowArray) {
      for (const key of Object.keys(row)) {
        columnSet.add(key)
      }
    }

    return { columns: [...columnSet], rows: rowArray }
  }, [data])

  const getRowKey = useCallback(
    (row: Record<string, unknown>, rowIndex: number) => {
      const contentKey = buildRowKey(row, columns)
      return contentKey ? `${contentKey}-${String(rowIndex)}` : `row-${String(rowIndex)}`
    },
    [columns]
  )

  return (
    <NxPanelContentStack>
      <NxScrollableTableContainer caption={ariaLabel} useFixedLayout={false} variant="compact">
        <Thead>
          <Tr>
            {columns.map((col) => (
              <Th key={col}>{renderHeader ? renderHeader(col) : col}</Th>
            ))}
          </Tr>
        </Thead>
        <Tbody>
          {rows.map((row, rowIndex) => (
            <Tr key={getRowKey(row, rowIndex)}>
              {columns.map((col) => {
                const text = toSafeString(row[col])
                return (
                  <Td key={col} dataLabel={col}>
                    {renderCell ? renderCell(text) : text}
                  </Td>
                )
              })}
            </Tr>
          ))}
        </Tbody>
      </NxScrollableTableContainer>
    </NxPanelContentStack>
  )
}
