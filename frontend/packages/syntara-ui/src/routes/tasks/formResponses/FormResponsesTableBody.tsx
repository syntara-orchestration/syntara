import { Flex, FlexItem } from '@patternfly/react-core'
import { RhUiCaretDownIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { ExpandableRowContent, Tbody, Td, Tr } from '@patternfly/react-table'
import { Fragment } from 'react'

import groupedTableStyles from '../../../components/groupedTable.module.css'
import { DateCell } from '../../../components/table/DateCell'
import { LinkCell } from '../../../components/table/LinkCell'
import { UserTimestamp } from '../../../components/table/UserTimestamp'
import type { ProjectRead } from '../../access/types'
import { buildWorkflowBuilderLink } from '../../approvals/buildWorkflowBuilderLink'

import { FormResponseExpandedDetail } from './FormResponseExpandedDetail'
import { FormResponseStatusBadges } from './formResponseStatusBadges'
import type { FormResponseListRow } from './useFormResponsesData'

function ActionedOnCell({ row }: Readonly<{ row: FormResponseListRow }>) {
  if (!row.responded_at) {
    return <DateCell dateString={null} />
  }

  return <UserTimestamp user={row.responded_by} timestamp={row.responded_at} inline />
}

function FormResponseRow({
  row,
  rowIndex,
  isExpanded,
  onToggleRow,
}: Readonly<{
  row: FormResponseListRow
  rowIndex: number
  isExpanded: boolean
  onToggleRow: (id: string) => void
}>) {
  const executionHref = `/executions/${row.execution_id}?form_prompt=${row.id}&history=closed`

  return (
    <Fragment key={row.id}>
      <Tr isContentExpanded={isExpanded}>
        <Td
          expand={{
            rowIndex,
            isExpanded,
            onToggle: () => onToggleRow(row.id),
          }}
        />
        <Td dataLabel="Name">
          <LinkCell href={executionHref}>{row.name || row.id}</LinkCell>
        </Td>
        <Td dataLabel="Workflow">
          {row.workflowId ? (
            <LinkCell href={buildWorkflowBuilderLink(row.workflowId, row.workflowVersion ?? undefined)}>
              {row.workflowName || row.workflowId}
            </LinkCell>
          ) : (
            (row.workflowName ?? '—')
          )}
        </Td>
        <Td dataLabel="Initiated">
          <DateCell dateString={row.created_at} />
        </Td>
        <Td dataLabel="Actioned on">
          <ActionedOnCell row={row} />
        </Td>
        <Td dataLabel="Status">
          <FormResponseStatusBadges status={row.status} />
        </Td>
      </Tr>
      <Tr isExpanded={isExpanded}>
        <Td colSpan={6}>
          <ExpandableRowContent>
            <FormResponseExpandedDetail row={row} isExpanded={isExpanded} />
          </ExpandableRowContent>
        </Td>
      </Tr>
    </Fragment>
  )
}

type ProjectGroup = {
  project: ProjectRead | null
  rows: FormResponseListRow[]
}

type FlatFormResponsesTableBodyProps = {
  rows: FormResponseListRow[]
  expandedRows: Set<string>
  onToggleRow: (id: string) => void
}

export function FlatFormResponsesTableBody({
  rows,
  expandedRows,
  onToggleRow,
}: Readonly<FlatFormResponsesTableBodyProps>) {
  return (
    <Tbody>
      {rows.map((row, index) => (
        <FormResponseRow
          key={row.id}
          row={row}
          rowIndex={index}
          isExpanded={expandedRows.has(row.id)}
          onToggleRow={onToggleRow}
        />
      ))}
    </Tbody>
  )
}

type GroupedFormResponsesTableBodyProps = {
  groupedRows: Map<string, ProjectGroup>
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
  expandedRows: Set<string>
  onToggleRow: (id: string) => void
}

export function GroupedFormResponsesTableBody({
  groupedRows,
  collapsedProjects,
  onToggleProject,
  expandedRows,
  onToggleRow,
}: Readonly<GroupedFormResponsesTableBodyProps>) {
  const rowIndexMap = new Map<string, number>()
  let globalIndex = 0
  for (const { rows } of groupedRows.values()) {
    for (const row of rows) {
      rowIndexMap.set(row.id, globalIndex++)
    }
  }

  return (
    <>
      {[...groupedRows.entries()].map(([projectId, { project, rows }]) => (
        <Tbody key={projectId}>
          <Tr className={groupedTableStyles.groupHeader} onClick={() => onToggleProject(projectId)}>
            <Td colSpan={6}>
              <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
                <FlexItem>{collapsedProjects.has(projectId) ? <RhUiCaretRightIcon /> : <RhUiCaretDownIcon />}</FlexItem>
                <FlexItem>
                  <strong>{project?.name ?? (projectId === 'unknown' ? 'No project' : projectId)}</strong>
                </FlexItem>
              </Flex>
            </Td>
          </Tr>
          {!collapsedProjects.has(projectId) &&
            rows.map((row) => (
              <FormResponseRow
                key={row.id}
                row={row}
                rowIndex={rowIndexMap.get(row.id) ?? 0}
                isExpanded={expandedRows.has(row.id)}
                onToggleRow={onToggleRow}
              />
            ))}
        </Tbody>
      ))}
    </>
  )
}
