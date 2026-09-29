import { Alert, Button, LabelGroup, StackItem, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ExpandableRowContent, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { ThProps } from '@patternfly/react-table'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { IconLabel } from '../../components/IconLabel'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynListPanelTable, SynListPanelToolbar, SynListPanelView } from '../../components/panels/list/SynListPanel'
import { SynEmptyStateFilter } from '../../components/states/SynEmptyStateFilter'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import type { KebabAction } from '../../components/SynKebabMenu'
import { SynKebabMenu } from '../../components/SynKebabMenu'
import { LinkCell } from '../../components/table/LinkCell'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useClientPagination } from '../../hooks/useClientPagination'
import { useColumnSortState } from '../../hooks/useColumnSortState'
import { useExpandableRowIds } from '../../hooks/useExpandableRowIds'
import { useFilterState } from '../../hooks/useFilterState'
import { useAlerts } from '../../providers/alerts'
import type { FilterConfig } from '../../types/filters'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { roleAssignmentsQueryKey } from '../access/useAlreadyAssignedRoles'
import { useAssignmentPermissions } from '../access/useAssignmentPermissions'

import { getProjectDetailPath } from './accessManagementPaths'
import { AssignRoleModal } from './AssignRoleModal'
import type { RoleAssignmentColumnKey, ColumnDefinition } from './roleAssignmentColumns'
import {
  allFilterFieldDefinitions,
  applyRoleAssignmentFilters,
  buildSortMaps,
  filterKeyToColumn,
  getVisibleColumns,
  sortRoleAssignmentRows,
} from './roleAssignmentColumns'
import styles from './RoleAssignmentsPanel.module.css'
import { principalTypeLabel, RolePrincipalType } from './RoleAssignmentTypes'
import type { RoleAssignmentRow } from './useRoleAssignmentData'
import { useRoleAssignmentData } from './useRoleAssignmentData'

export type { RoleAssignmentColumnKey } from './roleAssignmentColumns'

type RoleAssignmentsPanelProps = {
  principalType: RolePrincipalType
  principalId: string
  hiddenColumns?: RoleAssignmentColumnKey[]
  /** When rendered inside `SynListPanelTabs`, pass the tab `eventKey` for tabpanel ARIA. */
  tabKey?: string
  /** Accessible name for the tab panel; required when `tabKey` is set. */
  tabLabel?: string
}

function getAssignmentActions(
  row: RoleAssignmentRow,
  onUnassign: (row: RoleAssignmentRow) => void,
  permissions: ReturnType<typeof useAssignmentPermissions>
): KebabAction[] {
  return [
    {
      key: 'unassign',
      title: <IconLabel icon={<RhUiTrashIcon />}>Unassign role</IconLabel>,
      isDanger: true,
      isAriaDisabled: !permissions.canRevoke,
      tooltipProps: permissions.canRevoke ? undefined : { content: permissions.tooltips.revoke },
      onClick: permissions.canRevoke ? () => onUnassign(row) : undefined,
    },
  ]
}

function RoleAssignmentsTableBody({
  paginatedRows,
  getSortParams,
  onUnassign,
  permissions,
  visibleColumns,
  expandedRows,
  allRowsExpanded,
  onToggleRow,
  onCollapseAll,
}: Readonly<{
  paginatedRows: RoleAssignmentRow[]
  getSortParams: (columnIndex: number) => ThProps['sort']
  onUnassign: (row: RoleAssignmentRow) => void
  permissions: ReturnType<typeof useAssignmentPermissions>
  visibleColumns: ColumnDefinition[]
  expandedRows: Set<string>
  allRowsExpanded: boolean
  onToggleRow: (rowId: string) => void
  onCollapseAll: () => void
}>) {
  const isVisible = (key: RoleAssignmentColumnKey) => visibleColumns.some((col) => col.key === key)
  const sortIndex = (key: RoleAssignmentColumnKey) => visibleColumns.findIndex((col) => col.key === key)
  const expandableColumnCount = visibleColumns.length + 2

  return (
    <>
      <Thead>
        <Tr>
          <Th
            expand={{
              areAllExpanded: !allRowsExpanded,
              collapseAllAriaLabel: allRowsExpanded ? 'Collapse all' : 'Expand all',
              onToggle: onCollapseAll,
            }}
            aria-label="Row expansion"
          />
          {isVisible('roleName') && <Th sort={getSortParams(sortIndex('roleName'))}>Role name</Th>}
          {isVisible('description') && <Th sort={getSortParams(sortIndex('description'))}>Description</Th>}
          {isVisible('scope') && <Th sort={getSortParams(sortIndex('scope'))}>Scope</Th>}
          {isVisible('project') && <Th sort={getSortParams(sortIndex('project'))}>Project</Th>}
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      {paginatedRows.map((row, rowIndex) => {
        const isExpanded = expandedRows.has(row.id)
        return (
          <Tbody key={row.id} isExpanded={isExpanded}>
            <Tr isContentExpanded={isExpanded}>
              {row.policies.length > 0 ? (
                <Td
                  expand={{
                    rowIndex,
                    isExpanded,
                    onToggle: () => onToggleRow(row.id),
                  }}
                />
              ) : (
                <Td />
              )}
              {isVisible('roleName') && (
                <Td dataLabel="Role name">
                  <Truncate content={row.roleName} />
                </Td>
              )}
              {isVisible('description') && (
                <Td dataLabel="Description">
                  <Truncate content={row.roleDescription ?? '-'} />
                </Td>
              )}
              {isVisible('scope') && (
                <Td dataLabel="Scope">
                  <SynLabel color={row.scopeType === 'system' ? 'blue' : 'green'}>
                    {row.scopeType === 'system' ? 'System' : 'Project'}
                  </SynLabel>
                </Td>
              )}
              {isVisible('project') && (
                <Td dataLabel="Project">
                  {row.scopeType === 'project' && row.projectId ? (
                    <LinkCell href={getProjectDetailPath(row.projectId)}>
                      <Truncate content={row.scope} />
                    </LinkCell>
                  ) : (
                    '-'
                  )}
                </Td>
              )}
              <Td isActionCell>
                <SynKebabMenu
                  actions={getAssignmentActions(row, onUnassign, permissions)}
                  aria-label={`Actions for ${row.roleName} (${row.scope})`}
                />
              </Td>
            </Tr>
            {row.policies.length > 0 && (
              <Tr isExpanded={isExpanded}>
                <Td colSpan={expandableColumnCount}>
                  <ExpandableRowContent>
                    <LabelGroup isCompact numLabels={Infinity}>
                      {row.policies.map((policy) => (
                        <SynLabel key={policy.name} color="grey">
                          {policy.name}
                        </SynLabel>
                      ))}
                    </LabelGroup>
                  </ExpandableRowContent>
                </Td>
              </Tr>
            )}
          </Tbody>
        )
      })}
    </>
  )
}

export function RoleAssignmentsPanel({
  principalType,
  principalId,
  hiddenColumns,
  tabKey,
  tabLabel,
}: Readonly<RoleAssignmentsPanelProps>) {
  const queryClient = useQueryClient()
  const visibleColumns = useMemo(() => getVisibleColumns(hiddenColumns), [hiddenColumns])
  const sortMaps = useMemo(() => buildSortMaps(visibleColumns), [visibleColumns])
  const activeFilterFieldDefinitions = useMemo(() => {
    if (!hiddenColumns?.length) return allFilterFieldDefinitions
    return allFilterFieldDefinitions.filter((f) => !hiddenColumns.includes(filterKeyToColumn[f.key]))
  }, [hiddenColumns])

  const assignmentPermissions = useAssignmentPermissions()
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const openAssignIfAllowed = assignmentPermissions.canAssign ? () => setAssignModalOpen(true) : undefined
  const [rowToUnassign, setRowToUnassign] = useState<RoleAssignmentRow | null>(null)
  const { filters, setAllFilters, clearAllFilters } = useFilterState()
  const hasActiveFilters = filters.length > 0
  const { paginate, getFooterProps, resetPage } = useClientPagination()
  const { activeSortIndex, sortDirection, getSortParams } = useColumnSortState(sortMaps.sortFieldByColumn, resetPage)
  const { showAlert } = useAlerts()

  const { rows, queryForbidden, activeQuery, isLoading, deleteAssignment, refetch } = useRoleAssignmentData(
    principalType,
    principalId
  )

  const refetchAndInvalidateAuthz = useCallback(() => {
    invalidateAuthzCaches(queryClient)
    detachPromise(queryClient.invalidateQueries({ queryKey: roleAssignmentsQueryKey(principalType, principalId) }))
    refetch()
  }, [queryClient, principalType, principalId, refetch])

  const handleFilterChange = (newFilters: FilterConfig[]) => {
    setAllFilters(newFilters)
    resetPage()
  }

  const handleClearAllFiltersWithReset = useCallback(() => {
    clearAllFilters()
    resetPage()
  }, [clearAllFilters, resetPage])

  const filteredRows = useMemo(() => applyRoleAssignmentFilters(rows, filters), [rows, filters])

  const sortedRows = useMemo(
    () => sortRoleAssignmentRows(filteredRows, activeSortIndex, sortDirection, sortMaps),
    [filteredRows, activeSortIndex, sortDirection, sortMaps]
  )

  const paginatedRows = useMemo(() => paginate(sortedRows), [sortedRows, paginate])
  const tableFooter = useMemo(() => getFooterProps(sortedRows.length), [getFooterProps, sortedRows.length])

  const paginatedRowIds = useMemo(() => paginatedRows.map((row) => row.id), [paginatedRows])
  const { expandedRows, allRowsExpanded, handleToggleRow, handleCollapseAll } = useExpandableRowIds(paginatedRowIds)

  const handleUnassign = () => {
    if (!rowToUnassign) return
    deleteAssignment(rowToUnassign, {
      onSuccess: () => {
        showAlert({
          title: 'Role unassigned',
          description: `Role "${rowToUnassign.roleName}" has been unassigned.`,
          variant: 'success',
          autoDismiss: true,
        })
        refetchAndInvalidateAuthz()
      },
      onError: (err: unknown) => {
        showAlert({
          title: 'Failed to unassign role',
          description: getErrorMessage(err),
          variant: 'error',
          autoDismiss: true,
        })
      },
      onSettled: () => setRowToUnassign(null),
    })
  }

  const showToolbar = rows.length > 0 || hasActiveFilters || queryForbidden
  const isEmpty = rows.length === 0 && !queryForbidden

  const emptyStateSharedProps = {
    title: 'No role assignments yet',
    buttonText: 'Assign role',
    addData: openAssignIfAllowed,
  } as const
  const normalEmptyState = (
    <SynEmptyStateNoData
      {...emptyStateSharedProps}
      description={`No roles have been assigned to this ${principalTypeLabel[principalType]}.`}
    />
  )
  const forbiddenEmptyState = (
    <SynEmptyStateNoData
      {...emptyStateSharedProps}
      description={`No project-scoped roles have been assigned to this ${principalTypeLabel[principalType]}.`}
    />
  )

  const listBody =
    filteredRows.length === 0 ? (
      <StackItem isFilled>
        {queryForbidden ? (
          forbiddenEmptyState
        ) : (
          <SynEmptyStateFilter clearAllFilters={handleClearAllFiltersWithReset} />
        )}
      </StackItem>
    ) : (
      <SynListPanelTable caption="Role assignments table" footer={tableFooter} isExpandable>
        <RoleAssignmentsTableBody
          paginatedRows={paginatedRows}
          getSortParams={getSortParams}
          onUnassign={setRowToUnassign}
          permissions={assignmentPermissions}
          visibleColumns={visibleColumns}
          expandedRows={expandedRows}
          allRowsExpanded={allRowsExpanded}
          onToggleRow={handleToggleRow}
          onCollapseAll={handleCollapseAll}
        />
      </SynListPanelTable>
    )

  return (
    <>
      <SynListPanelView
        tabKey={tabKey}
        tabLabel={tabLabel}
        isPending={isLoading}
        error={activeQuery.isError && !queryForbidden ? activeQuery.error : null}
        onRetry={() => detachPromise(activeQuery.refetch())}
        errorTitle="Error loading role assignments"
        isEmpty={isEmpty}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFiltersWithReset}
        noDataState={normalEmptyState}
        toolbar={
          showToolbar ? (
            <>
              {queryForbidden && (
                <Alert
                  variant="info"
                  isInline
                  title="Showing project-scoped roles only"
                  className={styles.forbiddenAlert}
                >
                  System-level role assignments require administrator access. Only roles within your accessible projects
                  are shown.
                </Alert>
              )}
              <SynListPanelToolbar
                filterDefinitions={activeFilterFieldDefinitions}
                filters={filters}
                onFilterChange={handleFilterChange}
                clearAllFilters={handleClearAllFiltersWithReset}
                actions={
                  <DisabledWithTooltip
                    isDisabled={!assignmentPermissions.canAssign}
                    content={assignmentPermissions.tooltips.assign}
                  >
                    <Button
                      variant="primary"
                      icon={<RhUiAddIcon />}
                      isAriaDisabled={!assignmentPermissions.canAssign}
                      onClick={assignmentPermissions.canAssign ? () => setAssignModalOpen(true) : undefined}
                    >
                      Assign role
                    </Button>
                  </DisabledWithTooltip>
                }
              />
            </>
          ) : undefined
        }
        body={listBody}
      />

      <AssignRoleModal
        principalType={principalType}
        principalId={principalId}
        isOpen={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        onSuccess={refetchAndInvalidateAuthz}
      />

      <SynConfirmationDialog
        isOpen={!!rowToUnassign}
        onClose={() => setRowToUnassign(null)}
        onConfirm={handleUnassign}
        title="Unassign role?"
        confirmLabel="Unassign role"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        This unassigns the role <strong>{rowToUnassign?.roleName}</strong> from this principal. Related permissions will
        be revoked.
      </SynConfirmationDialog>
    </>
  )
}
