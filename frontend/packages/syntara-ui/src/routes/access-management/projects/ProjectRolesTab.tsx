import { Button, Label, LabelGroup, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditFillIcon, RhUiLockIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction, ThProps } from '@patternfly/react-table'
import { useState } from 'react'

import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { IconLabel } from '../../../components/IconLabel'
import {
  NxListPanel,
  NxListPanelTable,
  NxListPanelToolbar,
  NxListPanelView,
} from '../../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { useDialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { accessClient } from '../../access/accessClient'
import { builtinFilterDefinitions } from '../../access/builtinFilterDefinitions'
import type { ProjectRoleRead } from '../../access/types'
import { useBuiltinListState } from '../../access/useBuiltinListState'

import { AddProjectRoleDialog } from './AddProjectRoleDialog'
import { EditProjectRoleDialog } from './EditProjectRoleDialog'

const sortFieldByColumn: Record<number, string> = {
  0: 'name',
  3: 'is_builtin',
}

function ProjectRolesTable({
  roles,
  getSortParams,
  onEdit,
  onDelete,
}: Readonly<{
  roles: ProjectRoleRead[]
  getSortParams: (columnIndex: number) => ThProps['sort']
  onEdit: (role: ProjectRoleRead) => void
  onDelete: (role: ProjectRoleRead) => void
}>) {
  const getRoleActions = (role: ProjectRoleRead): IAction[] => [
    {
      title: <IconLabel icon={<RhUiEditFillIcon />}>Edit role</IconLabel>,
      onClick: () => onEdit(role),
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete role</IconLabel>,
      onClick: () => onDelete(role),
    },
  ]

  return (
    <>
      <Thead>
        <Tr>
          <Th sort={getSortParams(0)}>Name</Th>
          <Th>Description</Th>
          <Th>Policies</Th>
          <Th sort={getSortParams(3)} modifier="nowrap">
            Type
          </Th>
          <Th screenReaderText="Actions" />
        </Tr>
      </Thead>
      <Tbody>
        {roles.map((role) => (
          <Tr key={role.id}>
            <Td dataLabel="Name">
              <Truncate content={role.name} />
            </Td>
            <Td dataLabel="Description">
              <Truncate content={role.description ?? '-'} />
            </Td>
            <Td dataLabel="Policies">
              <LabelGroup isCompact numLabels={5}>
                {(role.policies ?? []).map((policy) => (
                  <Label key={policy} color="grey" isCompact>
                    {policy}
                  </Label>
                ))}
              </LabelGroup>
            </Td>
            <Td dataLabel="Type">
              {role.is_builtin ? (
                <Label color="grey" icon={<RhUiLockIcon />} isCompact>
                  Built-in
                </Label>
              ) : (
                <Label color="blue" isCompact>
                  Custom
                </Label>
              )}
            </Td>
            <Td isActionCell>{!role.is_builtin && <ActionsColumn items={getRoleActions(role)} />}</Td>
          </Tr>
        ))}
      </Tbody>
    </>
  )
}

export function ProjectRolesTab({ projectId }: Readonly<{ projectId: string }>) {
  const {
    filters,
    hasActiveFilters,
    handleFilterChange,
    clearAllFilters,
    getSortParams,
    queryParams,
    page,
    perPage,
    handlePerPageChange,
    goToPrevPage,
    goToNextPage,
  } = useBuiltinListState(sortFieldByColumn)
  const [roleToEdit, setRoleToEdit] = useState<ProjectRoleRead | null>(null)
  const deleteDialog = useDialogState<ProjectRoleRead>()
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const { showSuccess, showError } = useAlerts()

  const rolesQuery = accessClient.useQuery('get', '/projects/{project_id}/roles', {
    params: {
      path: { project_id: projectId },
      query: queryParams,
    },
  })

  const roles = rolesQuery.data?.resources ?? []

  const { mutate: deleteRole } = accessClient.useMutation('delete', '/projects/{project_id}/roles/{role_id}')

  const handleRolesChanged = () => {
    detachPromise(rolesQuery.refetch())
  }

  const handleDelete = (role: ProjectRoleRead | null) => {
    if (!role) return
    deleteRole(
      { params: { path: { project_id: projectId, role_id: role.id } } },
      {
        onSuccess: () => {
          showSuccess({ title: 'Role deleted', description: `Deleted role "${role.name}"` })
          handleRolesChanged()
        },
        onError: (error) => {
          showError({ title: 'Failed to delete role', description: getErrorMessage(error) })
        },
        onSettled: () => deleteDialog.close(),
      }
    )
  }

  return (
    <>
      <NxListPanel>
        <NxListPanelView
          isPending={rolesQuery.isPending}
          isFetching={rolesQuery.isFetching}
          error={rolesQuery.error}
          onRetry={() => detachPromise(rolesQuery.refetch())}
          isEmpty={roles.length === 0}
          hasActiveFilters={hasActiveFilters}
          onClearAllFilters={clearAllFilters}
          noDataState={
            <SynEmptyStateNoData
              title="No roles found"
              description="No roles are available for this project."
              buttonText="Add role"
              addData={() => setIsAddDialogOpen(true)}
            />
          }
          toolbar={
            roles.length > 0 || hasActiveFilters ? (
              <NxListPanelToolbar
                filters={filters}
                filterDefinitions={builtinFilterDefinitions}
                onFilterChange={handleFilterChange}
                clearAllFilters={clearAllFilters}
                actions={
                  <Button variant="primary" icon={<RhUiAddIcon />} onClick={() => setIsAddDialogOpen(true)}>
                    Add role
                  </Button>
                }
              />
            ) : undefined
          }
          body={
            <NxListPanelTable
              caption="Project roles"
              footer={{
                page,
                perPage,
                total: rolesQuery.data?.total ?? null,
                hasNext: !!rolesQuery.data?.next,
                onPrev: goToPrevPage,
                onNext: () => goToNextPage(rolesQuery.data?.next ?? null),
                onPerPageChange: handlePerPageChange,
              }}
            >
              <ProjectRolesTable
                roles={roles}
                getSortParams={getSortParams}
                onEdit={setRoleToEdit}
                onDelete={deleteDialog.open}
              />
            </NxListPanelTable>
          }
        />
      </NxListPanel>

      {isAddDialogOpen && (
        <AddProjectRoleDialog
          projectId={projectId}
          onClose={() => setIsAddDialogOpen(false)}
          onSuccess={handleRolesChanged}
        />
      )}

      {roleToEdit && (
        <EditProjectRoleDialog
          projectId={projectId}
          role={roleToEdit}
          onClose={() => setRoleToEdit(null)}
          onSuccess={handleRolesChanged}
        />
      )}

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
