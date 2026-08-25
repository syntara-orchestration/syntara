import { Spinner, StackItem } from '@patternfly/react-core'
import type { Approval } from '@syntara/contracts'
import { useMemo, useReducer, useState } from 'react'

import { EmptyStateAccessDenied } from '../../components/EmptyStateAccessDenied'
import { FilterBar } from '../../components/filters/FilterBar'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynPanelContentStack } from '../../components/layout/SynPanelContentStack'
import { useQueryState } from '../../components/states/useQueryState'
import { SynPageTitle } from '../../components/SynPageTitle'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useProjectsForGrouping } from '../../hooks/useProjectsForGrouping'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { getApprovalNameFilterDefinition, getApprovalStatusFilterDefinition } from './approvalFilters'
import { hasExpandableNotes } from './approvalNotes'
import { ApprovalsBulkActions } from './ApprovalsBulkActions'
import { ApprovalsContent } from './ApprovalsContent'
import { approvalsReducer } from './approvalsReducer'
import { approvalDefaultSort, approvalTableColumns } from './approvalTableColumns'
import { BulkActionDialogs } from './BulkActionDialogs'
import { canDecideOnApproval } from './canDecideOnApproval'
import { useApprovalDecideProjects } from './useApprovalDecideProjects'
import { useApprovalPermissions } from './useApprovalPermissions'
import { useApprovalsData } from './useApprovalsData'
import { useApprovalSelection } from './useApprovalSelection'
import { useBulkApprovalActions } from './useBulkApprovalActions'
import { useSelectableApprovalIds } from './useSelectableApprovalIds'

export type ApprovalWithDetails = Approval & {
  approvalName?: string
  workflowName?: string
  workflowId?: string
  workflowVersion?: number
}

export default function Approvals() {
  const approvalsDocLink = useDocLink('approvals')
  const permissions = useApprovalPermissions()

  // Show loading spinner while checking permissions
  if (permissions.isChecking) {
    return (
      <SynPage>
        <SynPageTitle segments={['Approvals']} />
        <SynPageHeader title="Approvals" docLink={approvalsDocLink ?? undefined} />
        <SynPageBody isCentered>
          <Spinner aria-label="Loading approval permissions" />
        </SynPageBody>
      </SynPage>
    )
  }

  // Show access denied if user lacks read permission
  if (!permissions.canRead) {
    return (
      <SynPage>
        <SynPageTitle segments={['Approvals']} />
        <SynPageHeader title="Approvals" docLink={approvalsDocLink ?? undefined} />
        <SynPageBody isCentered>
          <EmptyStateAccessDenied description="You do not have permission to view approvals. Contact your administrator to request access." />
        </SynPageBody>
      </SynPage>
    )
  }

  return <ApprovalsPage approvalsDocLink={approvalsDocLink} />
}

function ApprovalsPage({ approvalsDocLink }: { approvalsDocLink: string | null | undefined }) {
  const { selectedProjectId, stableProjectId, isAllProjects, projects, ProjectSelector } = useProjectSelector()
  const projectsForGrouping = useProjectsForGrouping(projects, isAllProjects)
  const [{ expandedRows }, dispatch] = useReducer(approvalsReducer, {
    expandedRows: new Set<string>(),
  })

  const projectExtraParams = useMemo(
    () => (selectedProjectId ? { project_id: selectedProjectId } : undefined),
    [selectedProjectId]
  )

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    getSortParams,
    sortParam,
  } = useCursorPagination({
    extraParams: projectExtraParams,
    defaultSort: approvalDefaultSort,
    columns: approvalTableColumns,
  })

  // Define filter field definitions for FilterBar
  const filterFieldDefinitions = useMemo(
    () => [getApprovalNameFilterDefinition(), getApprovalStatusFilterDefinition()],
    []
  )

  // Query approvals data
  const projectSelectorReady = isAllProjects || !!stableProjectId
  const { approvalsQuery, enrichedApprovals, groupedApprovals, sortedApprovals } = useApprovalsData({
    projectSelectorReady,
    isAllProjects,
    stableProjectId,
    queryParams,
    projects: projectsForGrouping,
  })

  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set())

  const toggleProjectCollapsed = (id: string) =>
    setCollapsedProjects((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  useCursorReset(enrichedApprovals.length, hasActiveFilters, cursor, approvalsQuery.isFetching, resetPagination)

  // Get per-project approval:decide permissions
  const {
    canDecideAllProjects,
    canDecideProjectNames,
    isLoading: isLoadingDecideProjects,
  } = useApprovalDecideProjects()

  // Compute per-approval permission flags
  const approvalPermissions = useMemo(() => {
    const map = new Map<string, boolean>()
    for (const approval of sortedApprovals) {
      map.set(approval.id, canDecideOnApproval(approval, canDecideAllProjects, canDecideProjectNames, projects))
    }
    return map
  }, [sortedApprovals, canDecideAllProjects, canDecideProjectNames, projects])

  // Only approvals with non-empty decision notes render an expand toggle
  const expandableApprovalIds = useMemo(
    () => sortedApprovals.filter(hasExpandableNotes).map((approval) => approval.id),
    [sortedApprovals]
  )

  // Compute which approvals are selectable (checkbox enabled) for select-all logic
  const selectableApprovalIds = useSelectableApprovalIds(sortedApprovals, approvalPermissions, isLoadingDecideProjects)

  // Selection state and handlers
  const {
    selectedApprovalIds,
    clearSelectedApprovalIds,
    handleSelectAll,
    handleSelectRow,
    pendingApprovals,
    allPendingSelected,
  } = useApprovalSelection(enrichedApprovals, sortedApprovals, {
    filters,
    sortParam,
    approvalPermissions,
    isLoadingPermissions: isLoadingDecideProjects,
    selectableApprovalIds,
  })

  // Bulk approval actions
  const {
    bulkApproveDialogOpen,
    setBulkApproveDialogOpen,
    bulkRejectDialogOpen,
    setBulkRejectDialogOpen,
    handleBulkApprove,
    handleBulkReject,
    isPending: isBulkActionPending,
  } = useBulkApprovalActions(selectedApprovalIds, () => {
    clearSelectedApprovalIds()
    detachPromise(approvalsQuery.refetch())
  })

  const queryState = useQueryState(approvalsQuery, {
    title: 'Error loading approvals',
    onRetry: () => detachPromise(approvalsQuery.refetch()),
  })

  // Show query state (loading/error)
  if (queryState) {
    return (
      <SynPage>
        <SynPageTitle segments={['Approvals']} />
        <SynPageHeader title="Approvals" docLink={approvalsDocLink ?? undefined} projectSelector={ProjectSelector} />
        <SynPageBody>
          <SynPanel isFullHeight>{queryState}</SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  const toggleRow = (approvalId: string) => dispatch({ type: 'TOGGLE_ROW', payload: approvalId })

  // Check if all expandable rows are currently expanded (rows without decision notes never expand)
  const hasExpandableRows = expandableApprovalIds.length > 0
  const allRowsExpanded = hasExpandableRows && expandableApprovalIds.every((id) => expandedRows.has(id))
  const collapseAllAriaLabel = allRowsExpanded ? 'Collapse all' : 'Expand all'

  const onCollapseAll = (_event: unknown, _rowIndex: number, isOpen: boolean) => {
    dispatch({
      type: 'SET_EXPANDED_ROWS',
      payload: isOpen ? new Set(expandableApprovalIds) : new Set<string>(),
    })
  }

  const isEmpty = sortedApprovals.length === 0

  return (
    <SynPage>
      <SynPageTitle segments={['Approvals']} />
      <SynPageHeader
        title="Approvals"
        docLink={approvalsDocLink ?? undefined}
        projectSelector={ProjectSelector}
        toolbar={
          !isEmpty || hasActiveFilters ? (
            <ApprovalsBulkActions
              selectedCount={selectedApprovalIds.size}
              onApprove={() => setBulkApproveDialogOpen(true)}
              onReject={() => setBulkRejectDialogOpen(true)}
              isDisabled={isBulkActionPending}
              permissionTooltip={
                !canDecideAllProjects && canDecideProjectNames.size === 0 && !isLoadingDecideProjects
                  ? permissionTooltip('approve or reject approvals', 'approval:decide')
                  : undefined
              }
            />
          ) : undefined
        }
      />

      <SynPageBody>
        <SynPanel isFullHeight>
          <SynPanelContentStack variant="inset">
            {(!isEmpty || hasActiveFilters) && (
              <StackItem>
                <FilterBar
                  fieldDefinitions={filterFieldDefinitions}
                  filters={filters}
                  onFilterChange={handleFilterChange}
                  showClearAll={true}
                />
              </StackItem>
            )}

            <ApprovalsContent
              sortedApprovals={sortedApprovals}
              hasActiveFilters={hasActiveFilters}
              handleClearAllFilters={handleClearAllFilters}
              expandedRows={expandedRows}
              onToggleRow={toggleRow}
              getSortParams={getSortParams}
              allRowsExpanded={allRowsExpanded}
              collapseAllAriaLabel={collapseAllAriaLabel}
              onCollapseAll={onCollapseAll}
              hasExpandableRows={hasExpandableRows}
              allPendingSelected={allPendingSelected}
              onSelectAll={handleSelectAll}
              hasPendingApprovals={pendingApprovals.length > 0}
              canDecideAnyApproval={canDecideAllProjects || canDecideProjectNames.size > 0}
              isAllProjects={isAllProjects}
              groupedApprovals={groupedApprovals}
              collapsedProjects={collapsedProjects}
              onToggleProject={toggleProjectCollapsed}
              selectedApprovalIds={selectedApprovalIds}
              onSelectRow={handleSelectRow}
              footerProps={getFooterProps(approvalsQuery.data)}
              approvalPermissions={approvalPermissions}
              isLoadingPermissions={isLoadingDecideProjects}
            />
          </SynPanelContentStack>
        </SynPanel>
      </SynPageBody>

      <BulkActionDialogs
        bulkApproveDialogOpen={bulkApproveDialogOpen}
        setBulkApproveDialogOpen={setBulkApproveDialogOpen}
        bulkRejectDialogOpen={bulkRejectDialogOpen}
        setBulkRejectDialogOpen={setBulkRejectDialogOpen}
        handleBulkApprove={handleBulkApprove}
        handleBulkReject={handleBulkReject}
        selectedCount={selectedApprovalIds.size}
        isBulkActionPending={isBulkActionPending}
      />
    </SynPage>
  )
}
