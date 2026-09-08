import type { ThProps } from '@patternfly/react-table'

import { SynPageBody } from '../../components/layout/SynPage'
import { SynEmptyStateFilter } from '../../components/states/SynEmptyStateFilter'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import type { PaginationFooterProps } from '../../components/table/PaginationFooter'
import { SynScrollableTableContainer } from '../../components/table/SynScrollableTableContainer'

import type { ApprovalWithDetails } from './Approvals'
import { FlatApprovalsTableBody, GroupedApprovalsTableBody } from './ApprovalsTableBody'
import { ApprovalsTableHead } from './ApprovalsTableHead'
import type { useApprovalsData } from './useApprovalsData'

export type ApprovalsContentProps = {
  sortedApprovals: ApprovalWithDetails[]
  hasActiveFilters: boolean
  handleClearAllFilters: () => void
  expandedRows: Set<string>
  onToggleRow: (approvalId: string) => void
  getSortParams: (columnField: string) => ThProps['sort']
  allRowsExpanded: boolean
  collapseAllAriaLabel: string
  onCollapseAll: (event: unknown, rowIndex: number, isOpen: boolean) => void
  hasExpandableRows: boolean
  allPendingSelected: boolean
  onSelectAll: (checked: boolean) => void
  hasPendingApprovals: boolean
  canDecideAnyApproval: boolean
  isAllProjects: boolean
  groupedApprovals: ReturnType<typeof useApprovalsData>['groupedApprovals']
  collapsedProjects: Set<string>
  onToggleProject: (id: string) => void
  selectedApprovalIds: Set<string>
  onSelectRow: (approval: ApprovalWithDetails, checked: boolean) => void
  footerProps: PaginationFooterProps
  approvalPermissions: Map<string, boolean>
  isLoadingPermissions: boolean
}

export function ApprovalsContent({
  sortedApprovals,
  hasActiveFilters,
  handleClearAllFilters,
  expandedRows,
  onToggleRow,
  getSortParams,
  allRowsExpanded,
  collapseAllAriaLabel,
  onCollapseAll,
  hasExpandableRows,
  allPendingSelected,
  onSelectAll,
  hasPendingApprovals,
  canDecideAnyApproval,
  isAllProjects,
  groupedApprovals,
  collapsedProjects,
  onToggleProject,
  selectedApprovalIds,
  onSelectRow,
  footerProps,
  approvalPermissions,
  isLoadingPermissions,
}: Readonly<ApprovalsContentProps>) {
  if (sortedApprovals.length === 0) {
    return (
      <SynPageBody isCentered>
        {hasActiveFilters ? (
          <SynEmptyStateFilter clearAllFilters={handleClearAllFilters} />
        ) : (
          <SynEmptyStateNoData
            title="No approvals yet"
            description="No approvals are currently pending or available."
          />
        )}
      </SynPageBody>
    )
  }

  return (
    <SynScrollableTableContainer caption="Approvals table" isExpandable footer={footerProps}>
      <ApprovalsTableHead
        getSortParams={getSortParams}
        allRowsExpanded={allRowsExpanded}
        collapseAllAriaLabel={collapseAllAriaLabel}
        onCollapseAll={onCollapseAll}
        hasExpandableRows={hasExpandableRows}
        showSelect={true}
        allPendingSelected={allPendingSelected}
        onSelectAll={onSelectAll}
        hasPendingApprovals={hasPendingApprovals}
        canDecideAnyApproval={canDecideAnyApproval}
        isLoadingPermissions={isLoadingPermissions}
      />
      {isAllProjects && groupedApprovals ? (
        <GroupedApprovalsTableBody
          groupedApprovals={groupedApprovals}
          collapsedProjects={collapsedProjects}
          onToggleProject={onToggleProject}
          expandedRows={expandedRows}
          onToggleRow={onToggleRow}
          showSelect={true}
          selectedApprovalIds={selectedApprovalIds}
          onSelectRow={onSelectRow}
          approvalPermissions={approvalPermissions}
          isLoadingPermissions={isLoadingPermissions}
        />
      ) : (
        <FlatApprovalsTableBody
          approvals={sortedApprovals}
          expandedRows={expandedRows}
          onToggleRow={onToggleRow}
          showSelect={true}
          selectedApprovalIds={selectedApprovalIds}
          onSelectRow={onSelectRow}
          approvalPermissions={approvalPermissions}
          isLoadingPermissions={isLoadingPermissions}
        />
      )}
    </SynScrollableTableContainer>
  )
}
