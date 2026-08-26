import { Button, Content, LabelGroup, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, ExpandableRowContent, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction, ThProps } from '@patternfly/react-table'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { NxConfirmationDialog } from '../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { IconLabel } from '../../components/IconLabel'
import { SynLabel } from '../../components/labels/SynLabel'
import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { useCursorReset } from '../../hooks/useCursorPagination'
import { useDialogState } from '../../hooks/useDialogState'
import { useExpandableRowIds } from '../../hooks/useExpandableRowIds'
import { useAlerts } from '../../providers/alerts'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { PrincipalNameCell } from '../access-management/PrincipalNameCell'
import { RolePrincipalType, principalTypeDisplay } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import { buildPermissionRow, transformAssignmentFilters } from './assignmentUtils'
import { AssignRoleDialog } from './AssignRoleDialog'
import { EditAssignmentDialog } from './EditAssignmentDialog'
import { ProjectLabel, ScopeLabel } from './ScopeLabel'
import type { PermissionRow } from './types'
import { useAccessTabQuery } from './useAccessTabQuery'
import { useAssignmentPermissions } from './useAssignmentPermissions'

const BASE_FILTER_FIELD_DEFS = [
  {
    key: 'name',
    label: 'Principal name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by principal name',
  },
  {
    key: 'role_name',
    label: 'Role name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by role name',
  },
  {
    key: 'type',
    label: 'Principal type',
    type: FilterTypeEnum.SELECT,
    options: [
      { value: RolePrincipalType.USER, label: 'User' },
      { value: RolePrincipalType.GROUP, label: 'Group' },
      { value: RolePrincipalType.SERVICE_ACCOUNT, label: 'Service account' },
    ],
    placeholder: 'Filter by principal type',
  },
  {
    key: 'scope',
    label: 'Scope',
    type: FilterTypeEnum.SELECT,
    options: [
      { value: 'system', label: 'System' },
      { value: 'project', label: 'Project' },
    ],
    placeholder: 'Filter by scope',
  },
  {
    key: 'project',
    label: 'Project',
    type: FilterTypeEnum.SELECT,
    options: [],
    placeholder: 'Filter by project',
  },
]

const SORT_FIELDS: Record<number, string> = {
  1: 'principal_name',
  2: 'principal_type',
  3: 'role_name',
  4: 'scope',
  5: 'project_name',
}

const EXPANDABLE_COLUMN_COUNT = 7

function getAssignmentRowActions(
  row: PermissionRow,
  permissions: ReturnType<typeof useAssignmentPermissions>,
  onEdit: (row: PermissionRow) => void,
  onDelete: (row: PermissionRow) => void
): IAction[] {
  return [
    {
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit assignment</IconLabel>,
      isAriaDisabled: !permissions.canAssign,
      tooltipProps: permissions.canAssign ? undefined : { content: permissions.tooltips.assign },
      onClick: permissions.canAssign ? () => onEdit(row) : undefined,
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete assignment</IconLabel>,
      isAriaDisabled: !permissions.canRevoke,
      tooltipProps: permissions.canRevoke ? undefined : { content: permissions.tooltips.revoke },
      onClick: permissions.canRevoke ? () => onDelete(row) : undefined,
    },
  ]
}

function AssignmentsTableBody({
  rows,
  projectNameMap,
  expandedRows,
  allRowsExpanded,
  onToggleRow,
  onCollapseAll,
  getSortParams,
  onEdit,
  onDelete,
  permissions,
}: Readonly<{
  rows: PermissionRow[]
  projectNameMap: Map<string, string>
  expandedRows: Set<string>
  allRowsExpanded: boolean
  onToggleRow: (rowKey: string) => void
  onCollapseAll: () => void
  getSortParams: (columnIndex: number) => ThProps['sort']
  onEdit: (row: PermissionRow) => void
  onDelete: (row: PermissionRow) => void
  permissions: ReturnType<typeof useAssignmentPermissions>
}>) {
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
          <Th sort={getSortParams(1)}>Principal name</Th>
          <Th sort={getSortParams(2)} modifier="nowrap">
            Principal type
          </Th>
          <Th sort={getSortParams(3)}>Role name</Th>
          <Th sort={getSortParams(4)} modifier="nowrap">
            Scope
          </Th>
          <Th sort={getSortParams(5)} modifier="nowrap">
            Project
          </Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      {rows.map((row, rowIndex) => {
        const rowKey = `${row.sourceEndpoint}-${row.id}`
        const isExpanded = expandedRows.has(rowKey)
        return (
          <Tbody key={rowKey} isExpanded={isExpanded}>
            <Tr isContentExpanded={isExpanded}>
              {row.rolePolicies.length > 0 ? (
                <Td
                  expand={{
                    rowIndex,
                    isExpanded,
                    onToggle: () => onToggleRow(rowKey),
                  }}
                />
              ) : (
                <Td />
              )}
              <Td dataLabel="Principal name">
                <PrincipalNameCell
                  principalType={row.principalType}
                  principalId={row.principalId}
                  name={row.principalName}
                />
              </Td>
              <Td dataLabel="Principal type">
                <SynLabel color={principalTypeDisplay[row.principalType].color}>
                  {principalTypeDisplay[row.principalType].text}
                </SynLabel>
              </Td>
              <Td dataLabel="Role name">
                <Truncate content={row.assignmentName} />
              </Td>
              <Td dataLabel="Scope">
                <ScopeLabel scope={row.scopeType} />
              </Td>
              <Td dataLabel="Project">
                <ProjectLabel projectId={row.projectId} projectNameMap={projectNameMap} />
              </Td>
              <Td isActionCell>
                <ActionsColumn items={getAssignmentRowActions(row, permissions, onEdit, onDelete)} />
              </Td>
            </Tr>
            {row.rolePolicies.length > 0 && (
              <Tr isExpanded={isExpanded}>
                <Td colSpan={EXPANDABLE_COLUMN_COUNT}>
                  <ExpandableRowContent>
                    <LabelGroup isCompact numLabels={Infinity}>
                      {row.rolePolicies.map((name) => (
                        <SynLabel key={name} color="grey">
                          {name}
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

export function AssignmentsTab() {
  const queryClient = useQueryClient()
  const permissions = useAssignmentPermissions()
  const { showSuccess, showError } = useAlerts()
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const deleteDialog = useDialogState<PermissionRow>()
  const editDialog = useDialogState<PermissionRow>()

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    getSortParams,
    projectNameMap,
    filterFieldDefinitions,
    queryParams,
  } = useAccessTabQuery({
    baseFilterDefs: BASE_FILTER_FIELD_DEFS,
    sortFields: SORT_FIELDS,
    defaultSortField: 'principal_name',
    initialSortIndex: 1,
    transformFilters: transformAssignmentFilters,
  })

  const assignmentsQuery = accessClient.useQuery('get', '/role_assignments', {
    params: { query: queryParams },
  })

  const { data, isPending, isFetching, error: queryError } = assignmentsQuery
  const rows = useMemo(() => (data?.resources ?? []).map(buildPermissionRow), [data?.resources])
  const rowIds = useMemo(() => rows.map((row) => `${row.sourceEndpoint}-${row.id}`), [rows])
  const { expandedRows, allRowsExpanded, handleToggleRow, handleCollapseAll } = useExpandableRowIds(rowIds)
  const refetch = useCallback(() => detachPromise(assignmentsQuery.refetch()), [assignmentsQuery])

  useCursorReset(rows.length, hasActiveFilters, cursor, isFetching, resetPagination)

  const { mutate: deleteRoleAssignment } = accessClient.useMutation('delete', '/role_assignments/{assignment_id}')
  const { mutate: deleteProjectRoleAssignment } = accessClient.useMutation(
    'delete',
    '/projects/{project_id}/role_assignments/{assignment_id}'
  )

  const handleDelete = (row: PermissionRow) => {
    const displayName = row.principalName
    const onSuccess = () => {
      showSuccess({ title: 'Permission removed', description: `Removed ${row.assignmentName} from ${displayName}` })
      detachPromise(queryClient.invalidateQueries({ queryKey: ['role-assignments'] }))
      refetch()
    }
    const onError = (error: unknown) => showError({ title: 'Remove failed', description: getErrorMessage(error) })
    const onSettled = deleteDialog.close
    const callbacks = { onSuccess, onError, onSettled }

    if (row.sourceEndpoint === 'project-role-assignments' && row.projectId) {
      deleteProjectRoleAssignment({ params: { path: { project_id: row.projectId, assignment_id: row.id } } }, callbacks)
    } else {
      deleteRoleAssignment({ params: { path: { assignment_id: row.id } } }, callbacks)
    }
  }

  const openAddDialog = permissions.canAssign ? () => setIsAddDialogOpen(true) : undefined
  const showToolbar = rows.length > 0 || hasActiveFilters
  const deleteItem = deleteDialog.item
  const editItem = editDialog.item

  return (
    <>
      <NxListPanelView
        tabKey="assignments"
        tabLabel="Assignments"
        isPending={isPending}
        isFetching={isFetching}
        error={queryError}
        onRetry={refetch}
        isEmpty={rows.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <SynEmptyStateNoData
            title="No assignments found"
            description="Assign roles to users or groups to grant access."
            buttonText="Add assignment"
            addData={openAddDialog}
          />
        }
        toolbar={
          showToolbar ? (
            <NxListPanelToolbar
              filters={filters}
              filterDefinitions={filterFieldDefinitions}
              onFilterChange={handleFilterChange}
              clearAllFilters={handleClearAllFilters}
              actions={
                <DisabledWithTooltip isDisabled={!permissions.canAssign} content={permissions.tooltips.assign}>
                  <Button
                    variant="primary"
                    icon={<RhUiAddIcon />}
                    isAriaDisabled={!permissions.canAssign}
                    onClick={openAddDialog}
                  >
                    Add assignment
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <>
            <Content>
              Assignments connect principals to roles, determining what each person can do. Each assignment can be
              scoped to a specific project or apply system-wide. Use this page to review, create, or revoke access in
              one place.
            </Content>
            <NxListPanelTable caption="Role assignments" isExpandable footer={getFooterProps(data)}>
              <AssignmentsTableBody
                rows={rows}
                projectNameMap={projectNameMap}
                expandedRows={expandedRows}
                allRowsExpanded={allRowsExpanded}
                onToggleRow={handleToggleRow}
                onCollapseAll={handleCollapseAll}
                getSortParams={getSortParams}
                onEdit={editDialog.open}
                onDelete={deleteDialog.open}
                permissions={permissions}
              />
            </NxListPanelTable>
          </>
        }
      />

      {isAddDialogOpen && <AssignRoleDialog onClose={() => setIsAddDialogOpen(false)} onSuccess={refetch} />}

      {deleteItem != null && (
        <NxConfirmationDialog
          isOpen={deleteDialog.isOpen}
          onClose={deleteDialog.close}
          onConfirm={() => handleDelete(deleteItem)}
          title="Remove assignment?"
          confirmLabel="Remove"
          confirmVariant="danger"
          titleIconVariant="warning"
        >
          This removes role <strong>{deleteItem.assignmentName}</strong> from{' '}
          <strong>{deleteItem.principalName}</strong>
          {deleteItem.scopeType === 'project' && (
            <>
              {' '}
              in project <strong>{deleteItem.scopeName}</strong>
            </>
          )}
          . The associated permissions will be revoked.
        </NxConfirmationDialog>
      )}

      {editItem != null && (
        <EditAssignmentDialog
          row={editItem}
          displayName={editItem.principalName}
          onClose={editDialog.close}
          onSuccess={refetch}
        />
      )}
    </>
  )
}
