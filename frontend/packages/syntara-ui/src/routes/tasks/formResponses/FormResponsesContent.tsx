import type { ThProps } from '@patternfly/react-table'

import { SynListPanelTable } from '../../../components/panels/list/SynListPanel'
import { ExpandableListTableColGroup } from '../../../components/table/ExpandableListTableColGroup'
import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'

import { FlatFormResponsesTableBody, GroupedFormResponsesTableBody } from './FormResponsesTableBody'
import { FormResponsesTableHead } from './FormResponsesTableHead'
import { FORM_RESPONSES_TABLE_DATA_COLUMN_COUNT } from './formResponseTableColumns'
import type { useFormResponsesData } from './useFormResponsesData'

export type FormResponsesContentProps = {
  sortedRows: ReturnType<typeof useFormResponsesData>['sortedRows']
  expandedRows: Set<string>
  onToggleRow: (id: string) => void
  getSortParams: (columnField: string) => ThProps['sort']
  allRowsExpanded: boolean
  collapseAllAriaLabel: string
  onCollapseAll: (event: unknown, rowIndex: number, isOpen: boolean) => void
  isAllProjects: boolean
  groupedRows: ReturnType<typeof useFormResponsesData>['groupedRows']
  collapsedProjects: Set<string>
  onToggleProject: (projectId: string) => void
  footerProps: PaginationFooterProps
}

export function FormResponsesContent({
  sortedRows,
  expandedRows,
  onToggleRow,
  getSortParams,
  allRowsExpanded,
  collapseAllAriaLabel,
  onCollapseAll,
  isAllProjects,
  groupedRows,
  collapsedProjects,
  onToggleProject,
  footerProps,
}: Readonly<FormResponsesContentProps>) {
  return (
    <SynListPanelTable caption="Form responses table" isExpandable footer={footerProps}>
      <ExpandableListTableColGroup dataColumnCount={FORM_RESPONSES_TABLE_DATA_COLUMN_COUNT} />
      <FormResponsesTableHead
        getSortParams={getSortParams}
        allRowsExpanded={allRowsExpanded}
        collapseAllAriaLabel={collapseAllAriaLabel}
        onCollapseAll={onCollapseAll}
      />
      {isAllProjects && groupedRows ? (
        <GroupedFormResponsesTableBody
          groupedRows={groupedRows}
          collapsedProjects={collapsedProjects}
          onToggleProject={onToggleProject}
          expandedRows={expandedRows}
          onToggleRow={onToggleRow}
        />
      ) : (
        <FlatFormResponsesTableBody rows={sortedRows} expandedRows={expandedRows} onToggleRow={onToggleRow} />
      )}
    </SynListPanelTable>
  )
}
