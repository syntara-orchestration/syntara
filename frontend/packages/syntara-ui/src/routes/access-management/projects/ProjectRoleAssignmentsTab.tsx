import { Button, LabelGroup, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction, ThProps } from '@patternfly/react-table'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynLabel } from '../../../components/labels/SynLabel'
import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { invalidateAuthzCaches } from '../../../hooks/invalidateAuthzCaches'
import { useCursorPagination, useCursorReset } from '../../../hooks/useCursorPagination'
import { useTableSort } from '../../../hooks/useTableSort'
import { useAlerts } from '../../../providers/alerts'
import type { FilterFieldDefinition } from '../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { accessClient } from '../../access/accessClient'
import { derivePrincipalType } from '../../access/assignmentUtils'
import type { RoleAssignmentRead } from '../../access/types'
import { useAssignmentPermissions } from '../../access/useAssignmentPermissions'
import { useRolePermissions } from '../../access/useRolePermissions'
import { PrincipalNameCell } from '../PrincipalNameCell'
import { principalTypeDisplay } from '../RoleAssignmentTypes'

import { AddProjectRoleDialog } from './AddProjectRoleDialog'
import { AssignProjectRoleModal } from './AssignProjectRoleModal'

const SORT_FIELDS = ['principal_name', 'role_name'] as const

const filterFieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'principal_name',
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
]

function getAssignmentActions(
  assignment: RoleAssignmentRead,
  onUnassign: (assignment: RoleAssignmentRead) => void,
  permissions: ReturnType<typeof useAssignmentPermissions>
): IAction[] {
  return [
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Unassign</IconLabel>,
      isAriaDisabled: !permissions.canRevoke,
      tooltipProps: permissions.canRevoke ? undefined : { content: permissions.tooltips.revoke },
      onClick: permissions.canRevoke ? () => onUnassign(assignment) : undefined,
    },
  ]
}

function RoleAssignmentsTable({
  assignments,
  getSortParams,
  onUnassign,
  permissions,
}: Readonly<{
  assignments: RoleAssignmentRead[]
  getSortParams: (columnIndex: number) => ThProps['sort']
  onUnassign: (assignment: RoleAssignmentRead) => void
  permissions: ReturnType<typeof useAssignmentPermissions>
}>) {
  return (
    <>
      <Thead>
        <Tr>
          <Th sort={getSortParams(0)}>Principal name</Th>
          <Th>Principal type</Th>
          <Th sort={getSortParams(1)}>Role name</Th>
          <Th>Policies</Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      <Tbody>
        {assignments.map((assignment) => {
          const principalType = derivePrincipalType(assignment)
          const { color, text } = principalTypeDisplay[principalType]
          const principalId = assignment.principal_id ?? assignment.group_id ?? ''
          return (
            <Tr key={assignment.id}>
              <Td dataLabel="Principal name">
                <PrincipalNameCell
                  principalType={principalType}
                  principalId={principalId}
                  name={assignment.principal_name}
                />
              </Td>
              <Td dataLabel="Principal type">
                <SynLabel color={color}>{text}</SynLabel>
              </Td>
              <Td dataLabel="Role name">
                <Truncate content={assignment.role_name} />
              </Td>
              <Td dataLabel="Policies">
                {(assignment.role_policies ?? []).length > 0 ? (
                  <LabelGroup numLabels={3}>
                    {(assignment.role_policies ?? []).map((name) => (
                      <SynLabel key={name}>{name}</SynLabel>
                    ))}
                  </LabelGroup>
                ) : (
                  '-'
                )}
              </Td>
              <Td isActionCell>
                <ActionsColumn items={getAssignmentActions(assignment, onUnassign, permissions)} />
              </Td>
            </Tr>
          )
        })}
      </Tbody>
    </>
  )
}

export function ProjectRoleAssignmentsTab({ projectId }: Readonly<{ projectId: string }>) {
  const queryClient = useQueryClient()
  const assignmentPermissions = useAssignmentPermissions({ resourceProject: projectId })
  const rolePermissions = useRolePermissions({ resourceProject: projectId })
  const { showAlert } = useAlerts()
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [createRoleOpen, setCreateRoleOpen] = useState(false)
  const [assignmentToUnassign, setAssignmentToUnassign] = useState<RoleAssignmentRead | null>(null)

  const {
    cursor,
    resetPagination,
    filters,
    hasActiveFilters,
    queryParams,
    handleFilterChange,
    handleClearAllFilters,
    getFooterProps,
  } = useCursorPagination()

  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialDirection: 'asc',
    onSortChange: resetPagination,
  })

  const finalQueryParams = useMemo(() => {
    const field = SORT_FIELDS[activeSortIndex] ?? 'principal_name'
    const sort = sortDirection === 'desc' ? `-${field}` : field
    return { ...queryParams, sort }
  }, [activeSortIndex, sortDirection, queryParams])

  const query = accessClient.useQuery('get', '/projects/{project_id}/role_assignments', {
    params: {
      path: { project_id: projectId },
      query: finalQueryParams,
    },
  })

  const assignments = useMemo(() => query.data?.resources ?? [], [query.data])

  useCursorReset(assignments.length, hasActiveFilters, cursor, query.isFetching, resetPagination)

  const refetch = useCallback(() => detachPromise(query.refetch()), [query])
  const refetchAndInvalidateAuthz = useCallback(() => {
    invalidateAuthzCaches(queryClient)
    refetch()
    detachPromise(queryClient.invalidateQueries({ queryKey: ['role-assignments'] }))
  }, [queryClient, refetch])

  const assignedRolesByPrincipal = useMemo(() => {
    const map = new Map<string, Set<string>>()
    for (const a of assignments) {
      const id = a.group_id ?? a.principal_id
      if (!id) continue
      const existing = map.get(id)
      if (existing) {
        existing.add(a.role_name)
      } else {
        map.set(id, new Set([a.role_name]))
      }
    }
    return map
  }, [assignments])

  const handleRoleCreated = useCallback(() => {
    detachPromise(queryClient.invalidateQueries({ queryKey: ['all-project-roles', projectId] }))
    invalidateAuthzCaches(queryClient)
    refetch()
  }, [queryClient, projectId, refetch])

  const { mutate: deleteAssignment } = accessClient.useMutation(
    'delete',
    '/projects/{project_id}/role_assignments/{assignment_id}'
  )

  const handleUnassign = () => {
    if (!assignmentToUnassign) return
    deleteAssignment(
      { params: { path: { project_id: projectId, assignment_id: assignmentToUnassign.id } } },
      {
        onSuccess: () => {
          showAlert({
            title: 'Role unassigned',
            description: `Role "${assignmentToUnassign.role_name}" has been unassigned from ${assignmentToUnassign.principal_name}.`,
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
        onSettled: () => setAssignmentToUnassign(null),
      }
    )
  }

  return (
    <>
      <NxListPanelView
        tabKey="role-assignments"
        tabLabel="Assignments"
        isPending={query.isPending}
        isFetching={query.isFetching}
        error={query.error}
        onRetry={refetch}
        isEmpty={assignments.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <SynEmptyStateNoData
            title="No role assignments"
            description="No roles have been assigned in this project."
            buttonText="Assign role"
            addData={assignmentPermissions.canAssign ? () => setAssignModalOpen(true) : undefined}
            secondaryActions={
              <DisabledWithTooltip isDisabled={!rolePermissions.canCreate} content={rolePermissions.tooltips.create}>
                <Button
                  variant="link"
                  isAriaDisabled={!rolePermissions.canCreate}
                  onClick={rolePermissions.canCreate ? () => setCreateRoleOpen(true) : undefined}
                >
                  Create role
                </Button>
              </DisabledWithTooltip>
            }
          />
        }
        toolbar={
          assignments.length > 0 || hasActiveFilters ? (
            <NxListPanelToolbar
              filters={filters}
              filterDefinitions={filterFieldDefinitions}
              onFilterChange={handleFilterChange}
              clearAllFilters={handleClearAllFilters}
              actions={
                <>
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
                  <DisabledWithTooltip
                    isDisabled={!rolePermissions.canCreate}
                    content={rolePermissions.tooltips.create}
                  >
                    <Button
                      variant="secondary"
                      isAriaDisabled={!rolePermissions.canCreate}
                      onClick={rolePermissions.canCreate ? () => setCreateRoleOpen(true) : undefined}
                    >
                      Create role
                    </Button>
                  </DisabledWithTooltip>
                </>
              }
            />
          ) : undefined
        }
        body={
          <NxListPanelTable caption="Project role assignments" footer={getFooterProps(query.data)}>
            <RoleAssignmentsTable
              assignments={assignments}
              getSortParams={getSortParams}
              onUnassign={setAssignmentToUnassign}
              permissions={assignmentPermissions}
            />
          </NxListPanelTable>
        }
      />

      <AssignProjectRoleModal
        projectId={projectId}
        isOpen={assignModalOpen}
        assignedRolesByPrincipal={assignedRolesByPrincipal}
        onClose={() => setAssignModalOpen(false)}
        onSuccess={refetchAndInvalidateAuthz}
      />

      <NxConfirmationDialog
        isOpen={!!assignmentToUnassign}
        onClose={() => setAssignmentToUnassign(null)}
        onConfirm={handleUnassign}
        title="Unassign role?"
        confirmLabel="Unassign"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        This unassigns the role <strong>{assignmentToUnassign?.role_name}</strong> from{' '}
        <strong>{assignmentToUnassign?.principal_name}</strong>. Related permissions will be revoked.
      </NxConfirmationDialog>

      {createRoleOpen && (
        <AddProjectRoleDialog
          projectId={projectId}
          onClose={() => setCreateRoleOpen(false)}
          onSuccess={handleRoleCreated}
        />
      )}
    </>
  )
}
