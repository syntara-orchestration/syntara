import { Alert, Button, Flex, FlexItem, LabelGroup, StackItem, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, ExpandableRowContent, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction, ThProps } from '@patternfly/react-table'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { FilterBar } from '../../components/filters'
import { IconLabel } from '../../components/IconLabel'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynPageBody } from '../../components/layout/SynPage'
import { SynPanelContentStack } from '../../components/layout/SynPanelContentStack'
import { SynEmptyStateFilter } from '../../components/states/SynEmptyStateFilter'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { SynErrorState } from '../../components/states/SynErrorState'
import { SynLoadingState } from '../../components/states/SynLoadingState'
import { LinkCell } from '../../components/table/LinkCell'
import { SynScrollableTableContainer } from '../../components/table/SynScrollableTableContainer'
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
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
}

function getAssignmentActions(
  row: RoleAssignmentRow,
  onUnassign: (row: RoleAssignmentRow) => void,
  permissions: ReturnType<typeof useAssignmentPermissions>
): IAction[] {
  return [
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Unassign</IconLabel>,
      isAriaDisabled: !permissions.canRevoke,
      tooltipProps: permissions.canRevoke ? undefined : { content: permissions.tooltips.revoke },
      onClick: permissions.canRevoke ? () => onUnassign(row) : undefined,
    },
  ]
}

function RoleAssignmentsTable({
  paginatedRows,
  sortedRows,
  page,
  perPage,
  getSortParams,
  onUnassign,
  onPrev,
  onNext,
  onPerPageChange,
  permissions,
  visibleColumns,
  expandedRows,
  allRowsExpanded,
  onToggleRow,
  onCollapseAll,
}: Readonly<{
  paginatedRows: RoleAssignmentRow[]
  sortedRows: RoleAssignmentRow[]
  page: number
  perPage: number
  getSortParams: (columnIndex: number) => ThProps['sort']
  onUnassign: (row: RoleAssignmentRow) => void
  onPrev: () => void
  onNext: () => void
  onPerPageChange: (perPage: number) => void
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
    <SynScrollableTableContainer
      caption="Role assignments table"
      isExpandable
      footer={{
        page,
        perPage,
        total: sortedRows.length,
        hasNext: page * perPage < sortedRows.length,
        onPrev,
        onNext,
        onPerPageChange,
      }}
    >
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
                <ActionsColumn items={getAssignmentActions(row, onUnassign, permissions)} />
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
    </SynScrollableTableContainer>
  )
}

function TableContent({
  filteredRows,
  rows,
  principalType,
  openAssignIfAllowed,
  clearAllFilters,
  resetPage,
  paginatedRows,
  sortedRows,
  page,
  perPage,
  getSortParams,
  onUnassign,
  onPrev,
  onNext,
  onPerPageChange,
  permissions,
  visibleColumns,
  expandedRows,
  allRowsExpanded,
  onToggleRow,
  onCollapseAll,
}: Readonly<{
  filteredRows: RoleAssignmentRow[]
  rows: RoleAssignmentRow[]
  principalType: RolePrincipalType
  openAssignIfAllowed: (() => void) | undefined
  clearAllFilters: () => void
  resetPage: () => void
  paginatedRows: RoleAssignmentRow[]
  sortedRows: RoleAssignmentRow[]
  page: number
  perPage: number
  getSortParams: (columnIndex: number) => ThProps['sort']
  onUnassign: (row: RoleAssignmentRow) => void
  onPrev: () => void
  onNext: () => void
  onPerPageChange: (perPage: number) => void
  permissions: ReturnType<typeof useAssignmentPermissions>
  visibleColumns: ColumnDefinition[]
  expandedRows: Set<string>
  allRowsExpanded: boolean
  onToggleRow: (rowId: string) => void
  onCollapseAll: () => void
}>) {
  if (filteredRows.length === 0) {
    if (rows.length === 0) {
      return (
        <SynPageBody isCentered>
          <SynEmptyStateNoData
            title="No role assignments yet"
            description={`No project-scoped roles have been assigned to this ${principalTypeLabel[principalType]}.`}
            buttonText="Assign role"
            addData={openAssignIfAllowed}
          />
        </SynPageBody>
      )
    }
    return (
      <SynPageBody isCentered>
        <SynEmptyStateFilter
          clearAllFilters={() => {
            clearAllFilters()
            resetPage()
          }}
        />
      </SynPageBody>
    )
  }

  return (
    <RoleAssignmentsTable
      paginatedRows={paginatedRows}
      sortedRows={sortedRows}
      page={page}
      perPage={perPage}
      getSortParams={getSortParams}
      onUnassign={onUnassign}
      onPrev={onPrev}
      onNext={onNext}
      onPerPageChange={onPerPageChange}
      permissions={permissions}
      visibleColumns={visibleColumns}
      expandedRows={expandedRows}
      allRowsExpanded={allRowsExpanded}
      onToggleRow={onToggleRow}
      onCollapseAll={onCollapseAll}
    />
  )
}

function ForbiddenAlert({ visible }: Readonly<{ visible: boolean }>) {
  if (!visible) return null
  return (
    <StackItem>
      <Alert variant="info" isInline title="Showing project-scoped roles only" className={styles.forbiddenAlert}>
        System-level role assignments require administrator access. Only roles within your accessible projects are
        shown.
      </Alert>
    </StackItem>
  )
}

export function RoleAssignmentsPanel({
  principalType,
  principalId,
  hiddenColumns,
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
  const { activeSortIndex, sortDirection, getSortParams } = useColumnSortState(sortMaps.sortFieldByColumn)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
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
    setPage(1)
  }

  const handlePerPageChange = (newPerPage: number) => {
    setPerPage(newPerPage)
    setPage(1)
  }

  const filteredRows = useMemo(() => applyRoleAssignmentFilters(rows, filters), [rows, filters])

  const sortedRows = useMemo(
    () => sortRoleAssignmentRows(filteredRows, activeSortIndex, sortDirection, sortMaps),
    [filteredRows, activeSortIndex, sortDirection, sortMaps]
  )

  const paginatedRows = useMemo(() => {
    const start = (page - 1) * perPage
    return sortedRows.slice(start, start + perPage)
  }, [sortedRows, page, perPage])

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

  // ── Loading / error states ──────────────────────────────────────────────
  if (activeQuery.isError && !queryForbidden) {
    return (
      <SynErrorState
        title="Error loading role assignments"
        message={activeQuery.error}
        onRetry={() => detachPromise(activeQuery.refetch())}
      />
    )
  }

  if (isLoading) return <SynLoadingState />

  if (rows.length === 0 && !queryForbidden) {
    return (
      <>
        <SynEmptyStateNoData
          title="No role assignments yet"
          description={`No roles have been assigned to this ${principalTypeLabel[principalType]}.`}
          buttonText="Assign role"
          addData={openAssignIfAllowed}
        />
        <AssignRoleModal
          principalType={principalType}
          principalId={principalId}
          isOpen={assignModalOpen}
          onClose={() => setAssignModalOpen(false)}
          onSuccess={refetchAndInvalidateAuthz}
        />
      </>
    )
  }

  return (
    <>
      <SynPanelContentStack>
        <ForbiddenAlert visible={queryForbidden} />

        <StackItem>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
            <FlexItem grow={{ default: 'grow' }}>
              <FilterBar
                fieldDefinitions={activeFilterFieldDefinitions}
                filters={filters}
                onFilterChange={handleFilterChange}
                showClearAll={true}
                clearAllFilters={() => {
                  clearAllFilters()
                  setPage(1)
                }}
              />
            </FlexItem>
            <FlexItem>
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
            </FlexItem>
          </Flex>
        </StackItem>

        <TableContent
          filteredRows={filteredRows}
          rows={rows}
          principalType={principalType}
          openAssignIfAllowed={openAssignIfAllowed}
          clearAllFilters={clearAllFilters}
          resetPage={() => setPage(1)}
          paginatedRows={paginatedRows}
          sortedRows={sortedRows}
          page={page}
          perPage={perPage}
          getSortParams={getSortParams}
          onUnassign={setRowToUnassign}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => p + 1)}
          onPerPageChange={handlePerPageChange}
          permissions={assignmentPermissions}
          visibleColumns={visibleColumns}
          expandedRows={expandedRows}
          allRowsExpanded={allRowsExpanded}
          onToggleRow={handleToggleRow}
          onCollapseAll={handleCollapseAll}
        />
      </SynPanelContentStack>

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
        confirmLabel="Unassign"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        This unassigns the role <strong>{rowToUnassign?.roleName}</strong> from this principal. Related permissions will
        be revoked.
      </SynConfirmationDialog>
    </>
  )
}
