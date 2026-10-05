import { useMemo, useReducer, useState } from 'react'

import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynListPanel, SynListPanelToolbar, SynListPanelView } from '../../components/panels/list/SynListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { SynPageTitle } from '../../components/SynPageTitle'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useProjectsForGrouping } from '../../hooks/useProjectsForGrouping'
import { detachPromise } from '../../utils/detachPromise'

import { getApprovalNameFilterDefinition, getApprovalStatusFilterDefinition } from './approvalFilters'
import { ApprovalsBulkActions } from './ApprovalsBulkActions'
import { ApprovalsContent } from './ApprovalsContent'
import { approvalsReducer } from './approvalsReducer'
import { approvalDefaultSort, approvalTableColumns } from './approvalTableColumns'
import { BulkActionDialogs } from './BulkActionDialogs'
import { canDecideOnApproval } from './canDecideOnApproval'
import { useApprovalDecideProjects } from './useApprovalDecideProjects'
import { useApprovalsData } from './useApprovalsData'
import { useApprovalSelection } from './useApprovalSelection'
import { useBulkApprovalActions } from './useBulkApprovalActions'
import { useSelectableApprovalIds } from './useSelectableApprovalIds'

type ApprovalsListPanelProps = {
  embedded?: boolean
  approvalsDocLink?: string | null
  tabKey?: string
  tabLabel?: string
}

export default function ApprovalsListPanel({
  embedded = false,
  approvalsDocLink,
  tabKey,
  tabLabel,
}: Readonly<ApprovalsListPanelProps>) {
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

  const filterFieldDefinitions = useMemo(
    () => [getApprovalNameFilterDefinition(), getApprovalStatusFilterDefinition()],
    []
  )

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

  useCursorReset({
    itemCount: enrichedApprovals.length,
    hasActiveFilters,
    cursor,
    isFetching: approvalsQuery.isFetching,
    resetPagination,
  })

  const {
    canDecideAllProjects,
    canDecideProjectNames,
    isLoading: isLoadingDecideProjects,
  } = useApprovalDecideProjects()

  const approvalPermissions = useMemo(() => {
    const map = new Map<string, boolean>()
    for (const approval of sortedApprovals) {
      map.set(approval.id, canDecideOnApproval(approval, canDecideAllProjects, canDecideProjectNames, projects))
    }
    return map
  }, [sortedApprovals, canDecideAllProjects, canDecideProjectNames, projects])

  const expandableApprovalIds = useMemo(() => sortedApprovals.map((approval) => approval.id), [sortedApprovals])

  const selectableApprovalIds = useSelectableApprovalIds(sortedApprovals, approvalPermissions, isLoadingDecideProjects)

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

  const toggleRow = (approvalId: string) => dispatch({ type: 'TOGGLE_ROW', payload: approvalId })

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
  const isPending = approvalsQuery.isPending

  const bulkActions =
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

  const listView = (
    <>
      <SynListPanelView
        tabKey={embedded ? tabKey : undefined}
        tabLabel={embedded ? tabLabel : undefined}
        isPending={isPending}
        isFetching={approvalsQuery.isFetching}
        error={approvalsQuery.error}
        errorTitle="Error loading approvals"
        onRetry={() => detachPromise(approvalsQuery.refetch())}
        isEmpty={isEmpty}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <SynEmptyStateNoData
            title="No approvals yet"
            description="No approvals are currently pending or available."
          />
        }
        toolbar={
          !isEmpty || hasActiveFilters ? (
            <SynListPanelToolbar
              filters={filters}
              filterDefinitions={filterFieldDefinitions}
              onFilterChange={handleFilterChange}
              clearAllFilters={handleClearAllFilters}
              actions={bulkActions}
            />
          ) : undefined
        }
        body={
          <ApprovalsContent
            sortedApprovals={sortedApprovals}
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
        }
      />

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
    </>
  )

  if (embedded) {
    return listView
  }

  return (
    <SynPage>
      <SynPageTitle segments={['Approvals']} />
      <SynPageHeader title="Approvals" docLink={approvalsDocLink ?? undefined} projectSelector={ProjectSelector} />
      <SynPageBody>
        <SynListPanel>{listView}</SynListPanel>
      </SynPageBody>
    </SynPage>
  )
}
