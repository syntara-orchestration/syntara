import { Badge, Button, Content, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiEditFillIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { Thead, Tbody, Tr, Th, Td, ActionsColumn } from '@patternfly/react-table'
import type { Group } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { usersClient } from '../../client'
import { NxConfirmationDialog } from '../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { IconLabel } from '../../components/IconLabel'
import { NxListPanelTable, NxListPanelToolbar, NxListPanelView } from '../../components/panels/list/NxListPanel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { DateCell } from '../../components/table/DateCell'
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useDeleteAction } from '../../hooks/useDeleteAction'
import { useDialogState } from '../../hooks/useDialogState'
import { useTableSort } from '../../hooks/useTableSort'
import type { FilterFieldDefinition } from '../../types/filters'
import { detachPromise } from '../../utils/detachPromise'

import { getGroupDescriptionFilterDefinition, getGroupNameFilterDefinition } from './groupFilters'
import { GroupFormModal } from './GroupFormModal'
import { useGroupPermissions } from './useGroupPermissions'

const SORT_FIELDS: Record<number, string> = {
  0: 'name',
  3: 'created_at',
  4: 'updated_at',
}

export function GroupsTab() {
  const navigate = useNavigate()
  const permissions = useGroupPermissions()
  const deleteDialog = useDialogState<Group>()
  const formDialog = useDialogState<Group | null>()

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

  const filterFieldDefinitions = useMemo<FilterFieldDefinition[]>(
    () => [getGroupNameFilterDefinition(), getGroupDescriptionFilterDefinition()],
    []
  )

  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialDirection: 'asc',
    onSortChange: resetPagination,
  })

  const finalQueryParams = useMemo(() => {
    const field = SORT_FIELDS[activeSortIndex] ?? 'name'
    const sort = sortDirection === 'desc' ? `-${field}` : field
    return { ...queryParams, sort }
  }, [queryParams, activeSortIndex, sortDirection])

  const query = usersClient.useQuery('get', '/groups', {
    params: {
      query: finalQueryParams,
    },
  })

  const data = query.data
  const groups = data?.resources ?? []

  useCursorReset(groups.length, hasActiveFilters, cursor, query.isFetching, resetPagination)

  const { mutate: deleteGroup } = usersClient.useMutation('delete', '/groups/{group_id}')

  const handleDelete = useDeleteAction({
    deleteFn: deleteGroup,
    buildParams: (group: Group) => ({ params: { path: { group_id: group.id } } }),
    entityLabel: 'group',
    getItemName: (group: Group) => group.name,
    onSuccess: () => {
      detachPromise(query.refetch())
    },
    onSettled: deleteDialog.close,
  })

  return (
    <>
      <NxListPanelView
        tabKey="groups"
        tabLabel="Groups"
        isPending={query.isPending}
        isFetching={query.isFetching}
        error={query.error}
        onRetry={() => detachPromise(query.refetch())}
        isEmpty={groups.length === 0}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={handleClearAllFilters}
        noDataState={
          <SynEmptyStateNoData
            title="No groups"
            description="Create a group to organize users and manage access."
            buttonText="Create group"
            addData={permissions.canCreate ? () => formDialog.open(null) : undefined}
          />
        }
        toolbar={
          groups.length > 0 || hasActiveFilters ? (
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
                    onClick={permissions.canCreate ? () => formDialog.open(null) : undefined}
                  >
                    Create group
                  </Button>
                </DisabledWithTooltip>
              }
            />
          ) : undefined
        }
        body={
          <>
            <Content>
              Groups organize users into logical collections, making it easy to assign roles to many users at once. When
              a role is assigned to a group, every user in that group inherits its permissions.
            </Content>
            <NxListPanelTable caption="Groups table" footer={getFooterProps(data)}>
              <Thead>
                <Tr>
                  <Th sort={getSortParams(0)}>Name</Th>
                  <Th>Description</Th>
                  <Th>Members</Th>
                  <Th sort={getSortParams(3)}>Created</Th>
                  <Th sort={getSortParams(4)}>Updated</Th>
                  <Th screenReaderText="Actions" />
                </Tr>
              </Thead>
              <Tbody>
                {groups.map((group) => (
                  <Tr key={group.id}>
                    <Td dataLabel="Name">
                      <Button
                        variant="link"
                        isInline
                        onClick={() =>
                          detachPromise(
                            navigate({ to: AppRoute.AccessManagement.GroupDetail.replace(':groupId', group.id ?? '') })
                          )
                        }
                      >
                        <Truncate content={group.name} />
                      </Button>
                    </Td>
                    <Td dataLabel="Description">
                      <Truncate content={group.description ?? ''} />
                    </Td>
                    <Td dataLabel="Members">
                      <Badge isRead>{group.member_count ?? 0}</Badge>
                    </Td>
                    <Td dataLabel="Created">
                      <DateCell dateString={group.created_at} />
                    </Td>
                    <Td dataLabel="Updated">
                      <DateCell dateString={group.updated_at} />
                    </Td>
                    <Td isActionCell>
                      {!group.is_builtin && (
                        <ActionsColumn
                          items={[
                            {
                              title: <IconLabel icon={<RhUiEditFillIcon />}>Edit</IconLabel>,
                              isAriaDisabled: !permissions.canUpdate,
                              tooltipProps: permissions.canUpdate
                                ? undefined
                                : { content: permissions.tooltips.update },
                              onClick: permissions.canUpdate ? () => formDialog.open(group as Group) : undefined,
                            },
                            { isSeparator: true },
                            {
                              title: <IconLabel icon={<RhUiTrashIcon />}>Delete</IconLabel>,
                              isAriaDisabled: !permissions.canDelete,
                              tooltipProps: permissions.canDelete
                                ? undefined
                                : { content: permissions.tooltips.delete },
                              onClick: permissions.canDelete ? () => deleteDialog.open(group as Group) : undefined,
                            },
                          ]}
                        />
                      )}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </NxListPanelTable>
          </>
        }
      />

      <GroupFormModal
        group={formDialog.item}
        isOpen={formDialog.isOpen}
        onClose={formDialog.close}
        onSuccess={() => {
          detachPromise(query.refetch())
        }}
      />

      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete group?"
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
        destructiveAcknowledgement={{
          checkboxId: 'delete-group-ack',
          label: 'I understand this group will be permanently deleted.',
        }}
      >
        The group <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
      </NxConfirmationDialog>
    </>
  )
}
