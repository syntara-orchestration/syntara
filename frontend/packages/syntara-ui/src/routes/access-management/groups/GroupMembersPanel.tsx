import { Button, Flex, FlexItem, StackItem, Truncate } from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction } from '@patternfly/react-table'
import { useMemo, useState } from 'react'

import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { FilterBar } from '../../../components/filters'
import { IconLabel } from '../../../components/IconLabel'
import { SynPageBody } from '../../../components/layout/SynPage'
import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'
import { SynEmptyStateFilter } from '../../../components/states/SynEmptyStateFilter'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { useQueryState } from '../../../components/states/useQueryState'
import { LinkCell } from '../../../components/table/LinkCell'
import { SynScrollableTableContainer } from '../../../components/table/SynScrollableTableContainer'
import { useFilterState } from '../../../hooks/useFilterState'
import { useAlerts } from '../../../providers/alerts'
import type { FilterFieldDefinition } from '../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { accessClient } from '../../access/accessClient'
import { getUserDetailPath } from '../accessManagementPaths'
import { DisabledBadge } from '../DisabledBadge'
import { MembershipSourceLabels } from '../MembershipSourceLabels'
import { getMembershipSources } from '../membershipSourceUtils'
import { useGroupPermissions } from '../useGroupPermissions'
import { userDisplayName } from '../users/userDisplayName'

import { AddMemberModal } from './AddMemberModal'

const filterFieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'username',
    label: 'Username',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by username',
  },
]

type GroupMembersPanelProps = {
  groupId: string
  onMembershipChange: () => void
}

type MemberInfo = {
  id: string
  username: string
}

function getMemberActions(
  member: MemberInfo,
  onRemove: (m: MemberInfo) => void,
  permissions: ReturnType<typeof useGroupPermissions>
): IAction[] {
  return [
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Remove</IconLabel>,
      isAriaDisabled: !permissions.canManageMembers,
      tooltipProps: permissions.canManageMembers ? undefined : { content: permissions.tooltips.manageMembers },
      onClick: permissions.canManageMembers ? () => onRemove(member) : undefined,
    },
  ]
}

function useGroupMembersData(groupId: string, onMembershipChange: () => void) {
  const { showAlert } = useAlerts()
  const query = accessClient.useQuery('get', '/groups/{group_id}/members', {
    params: { path: { group_id: groupId } },
  })
  const members = useMemo(() => query.data?.resources ?? [], [query.data])
  const { mutate: removeMember } = accessClient.useMutation('delete', '/groups/{group_id}/members/{user_id}')

  const remove = (member: MemberInfo, onSettled: () => void) => {
    removeMember(
      { params: { path: { group_id: groupId, user_id: member.id } } },
      {
        onSuccess: () => {
          showAlert({
            title: 'Member removed',
            description: `User "${member.username}" has been removed from the group.`,
            variant: 'success',
            autoDismiss: true,
          })
          detachPromise(query.refetch())
          onMembershipChange()
        },
        onError: (err: unknown) => {
          showAlert({
            title: 'Failed to remove member',
            description: getErrorMessage(err),
            variant: 'error',
            autoDismiss: true,
          })
        },
        onSettled,
      }
    )
  }

  const handleMemberAdded = () => {
    detachPromise(query.refetch())
    onMembershipChange()
  }

  return { query, members, remove, handleMemberAdded }
}

export function GroupMembersPanel({ groupId, onMembershipChange }: Readonly<GroupMembersPanelProps>) {
  const permissions = useGroupPermissions()
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [memberToRemove, setMemberToRemove] = useState<MemberInfo | null>(null)
  const { filters, setAllFilters, clearAllFilters } = useFilterState()
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const { query, members, remove, handleMemberAdded } = useGroupMembersData(groupId, onMembershipChange)

  const filteredMembers = useMemo(() => {
    const nameFilter = filters.find((f) => f.key === 'username')
    if (!nameFilter) return members
    const term = String(nameFilter.value).toLowerCase()
    return members.filter((m) => m.username.toLowerCase().includes(term))
  }, [members, filters])

  const paginatedMembers = useMemo(() => {
    const start = (page - 1) * perPage
    return filteredMembers.slice(start, start + perPage)
  }, [filteredMembers, page, perPage])

  const handleRemove = () => {
    if (!memberToRemove) return
    remove(memberToRemove, () => setMemberToRemove(null))
  }

  const queryState = useQueryState(query, {
    title: 'Error loading members',
    onRetry: () => detachPromise(query.refetch()),
  })
  if (queryState) return queryState

  if (members.length === 0) {
    return (
      <>
        <SynEmptyStateNoData
          title="No members"
          description="Add users to this group to manage their access."
          buttonText="Add member"
          addData={permissions.canManageMembers ? () => setAddModalOpen(true) : undefined}
        />
        <AddMemberModal
          groupId={groupId}
          isOpen={addModalOpen}
          onClose={() => setAddModalOpen(false)}
          onSuccess={handleMemberAdded}
          existingMemberIds={[]}
        />
      </>
    )
  }

  return (
    <>
      <SynPanelContentStack>
        <StackItem>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
            <FlexItem grow={{ default: 'grow' }}>
              <FilterBar
                fieldDefinitions={filterFieldDefinitions}
                filters={filters}
                onFilterChange={(f) => {
                  setAllFilters(f)
                  setPage(1)
                }}
                showClearAll={true}
                clearAllFilters={() => {
                  clearAllFilters()
                  setPage(1)
                }}
              />
            </FlexItem>
            <FlexItem>
              <DisabledWithTooltip
                isDisabled={!permissions.canManageMembers}
                content={permissions.tooltips.manageMembers}
              >
                <Button
                  variant="primary"
                  icon={<RhUiAddIcon />}
                  isAriaDisabled={!permissions.canManageMembers}
                  onClick={permissions.canManageMembers ? () => setAddModalOpen(true) : undefined}
                >
                  Add member
                </Button>
              </DisabledWithTooltip>
            </FlexItem>
          </Flex>
        </StackItem>

        {filteredMembers.length === 0 ? (
          <SynPageBody isCentered>
            <SynEmptyStateFilter
              clearAllFilters={() => {
                clearAllFilters()
                setPage(1)
              }}
            />
          </SynPageBody>
        ) : (
          <SynScrollableTableContainer
            caption="Group members table"
            footer={{
              page,
              perPage,
              total: filteredMembers.length,
              hasNext: page * perPage < filteredMembers.length,
              onPrev: () => setPage((p) => Math.max(1, p - 1)),
              onNext: () => setPage((p) => p + 1),
              onPerPageChange: (n: number) => {
                setPerPage(n)
                setPage(1)
              },
            }}
          >
            <Thead>
              <Tr>
                <Th>Username</Th>
                <Th>Name</Th>
                <Th>Email</Th>
                <Th>Source</Th>
                <Th screenReaderText="Actions" />
              </Tr>
            </Thead>
            <Tbody>
              {paginatedMembers.map((member) => (
                <Tr key={member.id}>
                  <Td dataLabel="Username">
                    <LinkCell href={getUserDetailPath(member.id)}>
                      <Truncate content={member.username} />
                    </LinkCell>
                    {!member.is_enabled && <DisabledBadge />}
                  </Td>
                  <Td dataLabel="Name">
                    <Truncate content={userDisplayName(member)} />
                  </Td>
                  <Td dataLabel="Email">
                    <Truncate content={member.email ?? ''} />
                  </Td>
                  <Td dataLabel="Source">
                    <MembershipSourceLabels sources={getMembershipSources(member)} />
                  </Td>
                  <Td isActionCell>
                    {!member.is_builtin && (
                      <ActionsColumn
                        items={getMemberActions(
                          { id: member.id, username: member.username },
                          setMemberToRemove,
                          permissions
                        )}
                      />
                    )}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </SynScrollableTableContainer>
        )}
      </SynPanelContentStack>

      <AddMemberModal
        groupId={groupId}
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={handleMemberAdded}
        existingMemberIds={members.map((m) => m.id)}
      />

      <NxConfirmationDialog
        isOpen={!!memberToRemove}
        onClose={() => setMemberToRemove(null)}
        onConfirm={handleRemove}
        title="Remove member?"
        confirmLabel="Remove"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        This removes <strong>{memberToRemove?.username}</strong> from the group. They will lose any permissions granted
        through this group membership.
      </NxConfirmationDialog>
    </>
  )
}
