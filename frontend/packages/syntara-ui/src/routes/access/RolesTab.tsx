import { Button, Content, LabelGroup } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditFillIcon, RhUiLockIcon, RhUiTrashIcon } from '@patternfly/react-icons'
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
import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { useColumnSortState } from '../../hooks/useColumnSortState'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useDeleteAction } from '../../hooks/useDeleteAction'
import { useDialogState } from '../../hooks/useDialogState'
import { FilterOperatorEnum, FilterTypeEnum } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'
import { buildFilterParams } from '../../utils/filterUtils'

import { accessClient } from './accessClient'
import { AddRoleDialog } from './AddRoleDialog'
import { POLICY_NAME_FILTER_DEF } from './builtinFilterDefinitions'
import { EditRoleDialog } from './EditRoleDialog'
import { buildProjectFilterDefs, ROLE_SCOPE_OPTIONS, transformFiltersForApi } from './scopeFilterUtils'
import { ProjectLabel, ScopeLabel } from './ScopeLabel'
import type { RoleRead } from './types'
import { useProjectNameMap } from './useProjectNameMap'
import { useRolePermissions } from './useRolePermissions'

const BASE_FILTER_FIELD_DEFS = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
  {
    key: 'scope',
    label: 'Scope',
    type: FilterTypeEnum.SELECT,
    options: ROLE_SCOPE_OPTIONS,
    placeholder: 'Filter by scope',
  },
  {
    key: 'project',
    label: 'Project',
    type: FilterTypeEnum.SELECT,
    options: [],
    placeholder: 'Filter by project',
  },
  POLICY_NAME_FILTER_DEF,
  {
    key: 'type',
    label: 'Type',
    type: FilterTypeEnum.SELECT,
    options: [
      { value: 'builtin', label: 'Built-in' },
      { value: 'custom', label: 'Custom' },
    ],
    placeholder: 'Filter by type',
  },
]

const SORT_FIELDS: Record<number, string> = {
  1: 'name',
  3: 'scope',
  4: 'project_id',
  5: 'is_builtin',
}

function getRoleActions(
  role: RoleRead,
  onEdit: (r: RoleRead) => void,
  onDelete: (r: RoleRead) => void,
  permissions: ReturnType<typeof useRolePermissions>
): IAction[] {
  return [
    {
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit role</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
      onClick: permissions.canUpdate ? () => onEdit(role) : undefined,
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete role</IconLabel>,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: permissions.canDelete ? () => onDelete(role) : undefined,
    },
  ]
}

const EXPANDABLE_COLUMN_COUNT = 7

function RolesTable({
  roles,
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
  roles: RoleRead[]
  projectNameMap: Map<string, string>
  expandedRows: Set<string>
  allRowsExpanded: boolean
  onToggleRow: (roleId: string) => void
  onCollapseAll: () => void
  getSortParams: (columnIndex: number) => ThProps['sort']
  onEdit: (role: RoleRead) => void
  onDelete: (role: RoleRead) => void
  permissions: ReturnType<typeof useRolePermissions>
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
          <Th sort={getSortParams(1)}>Name</Th>
          <Th>Description</Th>
          <Th sort={getSortParams(3)} modifier="nowrap">
            Scope
          </Th>
          <Th sort={getSortParams(4)} modifier="nowrap">
            Project
          </Th>
          <Th sort={getSortParams(5)} modifier="nowrap">
            Type
          </Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      {roles.map((role, rowIndex) => {
        const isExpanded = expandedRows.has(role.id)
        return (
          <Tbody key={role.id} isExpanded={isExpanded}>
            <Tr isContentExpanded={isExpanded}>
              <Td
                expand={{
                  rowIndex,
                  isExpanded,
                  onToggle: () => onToggleRow(role.id),
                }}
              />
              <Td dataLabel="Name">{role.name}</Td>
              <Td dataLabel="Description">{role.description ?? '-'}</Td>
              <Td dataLabel="Scope">
                <ScopeLabel scope={role.scope} />
              </Td>
              <Td dataLabel="Project">
                <ProjectLabel projectId={role.project_id} projectNameMap={projectNameMap} />
              </Td>
              <Td dataLabel="Type">
                {role.is_builtin ? (
                  <SynLabel color="grey" icon={<RhUiLockIcon />}>
                    Built-in
                  </SynLabel>
                ) : (
                  <SynLabel color="blue">Custom</SynLabel>
                )}
              </Td>
              <Td isActionCell>
                {!role.is_builtin && <ActionsColumn items={getRoleActions(role, onEdit, onDelete, permissions)} />}
              </Td>
            </Tr>
            <Tr isExpanded={isExpanded}>
              <Td colSpan={EXPANDABLE_COLUMN_COUNT}>
                <ExpandableRowContent>
                  <LabelGroup isCompact numLabels={Infinity}>
                    {(role.policies ?? []).map((policy) => (
                      <SynLabel key={policy} color="grey">
                        {policy}
                      </SynLabel>
                    ))}
                  </LabelGroup>
                </ExpandableRowContent>
              </Td>
            </Tr>
          </Tbody>
        )
      })}
    </>
  )
}

export function RolesTab() {
  const queryClient = useQueryClient()
  const permissions = useRolePermissions()

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
    perPage,
  } = useCursorPagination()

  const { sortParam, getSortParams } = useColumnSortState(SORT_FIELDS, resetPagination)

  const editDialog = useDialogState<RoleRead>()
  const deleteDialog = useDialogState<RoleRead>()
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  const { projectNameMap } = useProjectNameMap()

  const filterFieldDefinitions = useMemo(
    () => buildProjectFilterDefs([...BASE_FILTER_FIELD_DEFS], projectNameMap),
    [projectNameMap]
  )

  const queryParams = useMemo(() => {
    const params: Record<string, unknown> = { limit: perPage, include_total: true }
    if (sortParam) params.sort = sortParam
    if (cursor) params.cursor = cursor
    Object.assign(params, buildFilterParams(transformFiltersForApi(filters)))
    return params
  }, [sortParam, perPage, cursor, filters])

  const rolesQuery = accessClient.useQuery('get', '/roles', {
    params: { query: queryParams },
  })

  const data = rolesQuery.data
  const roles = useMemo(() => data?.resources ?? [], [data?.resources])
  // List refresh only — do not invalidate authz caches on every refetch/retry.
  const refetch = useCallback(() => detachPromise(rolesQuery.refetch()), [rolesQuery])
  const onRoleDeleted = useCallback(() => {
    invalidateAuthzCaches(queryClient)
    refetch()
  }, [queryClient, refetch])

  useCursorReset(roles.length, hasActiveFilters, cursor, rolesQuery.isFetching, resetPagination)

  const allRowsExpanded = roles.length > 0 && roles.every((r) => expandedRows.has(r.id))

  const handleToggleRow = useCallback((roleId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(roleId)) {
        next.delete(roleId)
      } else {
        next.add(roleId)
      }
      return next
    })
  }, [])

  const handleCollapseAll = useCallback(() => {
    if (allRowsExpanded) {
      setExpandedRows(new Set())
    } else {
      setExpandedRows(new Set(roles.map((r) => r.id)))
    }
  }, [allRowsExpanded, roles])

  const { mutate: deleteRole } = accessClient.useMutation('delete', '/roles/{role_id}')

  const handleDelete = useDeleteAction({
    deleteFn: deleteRole,
    buildParams: (role: RoleRead) => ({ params: { path: { role_id: role.id } } }),
    entityLabel: 'role',
    getItemName: (role: RoleRead) => role.name,
    onSuccess: onRoleDeleted,
    onSettled: deleteDialog.close,
  })

  return (
    <>
      <NxListPanelView
        tabKey="roles"
        tabLabel="Roles"
        isPending={rolesQuery.isPending}
        isFetching={rolesQuery.isFetching}
        error={rolesQuery.error}
        onRetry={refetch}
        isEmpty={roles.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={<SynEmptyStateNoData title="No roles yet" description="No roles are available." />}
        toolbar={
          roles.length > 0 || hasActiveFilters ? (
            <NxListPanelToolbar
              filters={filters}
              filterDefinitions={filterFieldDefinitions}
              onFilterChange={handleFilterChange}
              clearAllFilters={handleClearAllFilters}
              actions={
                <DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
                  <Button
                    variant="primary"
                    icon={<RhUiAddIcon />}
                    isAriaDisabled={!permissions.canCreate}
                    onClick={permissions.canCreate ? () => setIsAddDialogOpen(true) : undefined}
                  >
                    Create role
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <>
            <Content>
              Roles bundle one or more policies together so they can be assigned to users and groups as a unit at the
              system or project level. Assign roles system-wide for broad access, or scope them to specific projects for
              tighter control.
            </Content>
            <NxListPanelTable caption="Roles" isExpandable footer={getFooterProps(data)}>
              <RolesTable
                roles={roles}
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

      {isAddDialogOpen && <AddRoleDialog onClose={() => setIsAddDialogOpen(false)} onSuccess={refetch} />}

      {editDialog.item && <EditRoleDialog role={editDialog.item} onClose={editDialog.close} onSuccess={refetch} />}

      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete role?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-role-ack',
          label: 'I understand this role will be permanently deleted.',
        }}
      >
        The role <strong>{deleteDialog.item?.name}</strong> will be deleted. Assignments that use this role will lose
        access. This cannot be undone.
      </NxConfirmationDialog>
    </>
  )
}
