import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  Flex,
  FlexItem,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  StackItem,
  Truncate,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction } from '@patternfly/react-table'
import type { Group } from '@syntara/contracts'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { FilterBar } from '../../../components/filters'
import { IconLabel } from '../../../components/IconLabel'
import { NxLabel } from '../../../components/labels/NxLabel'
import { SynPageBody } from '../../../components/layout/SynPage'
import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'
import { NxEmptyStateFilter } from '../../../components/states/NxEmptyStateFilter'
import { NxEmptyStateNoData } from '../../../components/states/NxEmptyStateNoData'
import { useQueryState } from '../../../components/states/useQueryState'
import { LinkCell } from '../../../components/table/LinkCell'
import { NxScrollableTableContainer } from '../../../components/table/NxScrollableTableContainer'
import { useFilterState } from '../../../hooks/useFilterState'
import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import type { FilterFieldDefinition } from '../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { accessClient } from '../../access/accessClient'
import { TypeaheadSelect } from '../../access/TypeaheadSelect'
import { useAllGroups } from '../../access/useAllGroups'
import { getGroupDetailPath } from '../accessManagementPaths'
import { BUILTIN_AUTHENTICATED_GROUP_NAME } from '../adminConstants'
import { MembershipSourceLabels } from '../MembershipSourceLabels'
import { getMembershipSources } from '../membershipSourceUtils'
import { useGroupPermissions } from '../useGroupPermissions'

const filterFieldDefinitions: FilterFieldDefinition[] = [
  {
    key: 'name',
    label: 'Name',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by name',
  },
  {
    key: 'description',
    label: 'Description',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by description',
  },
]

type UserGroupsPanelProps = {
  userId: string
}

type GroupInfo = {
  id: string
  name: string
}

const addToGroupSchema = z.object({
  groupId: z.string().min(1, 'Group is required'),
})

type AddToGroupFormData = z.infer<typeof addToGroupSchema>

function AddToGroupModal({
  userId,
  isOpen,
  onClose,
  onSuccess,
  existingGroupIds,
}: Readonly<{
  userId: string
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  existingGroupIds: string[]
}>) {
  const { showSuccess } = useAlerts()

  const { handleSubmit, control, reset, setError } = useForm<AddToGroupFormData>({
    resolver: zodResolver(addToGroupSchema, undefined, { mode: 'sync' }),
    defaultValues: { groupId: '' },
  })

  const handleError = useFormMutationErrorHandler<AddToGroupFormData>(setError)

  const { groups: allGroupsForPicker } = useAllGroups()

  const availableGroups = useMemo(() => {
    return allGroupsForPicker
      .filter((g): g is typeof g & { id: string } => !!g.id && !existingGroupIds.includes(g.id))
      .map((g) => ({
        value: g.id,
        label: g.name,
        description: g.description ?? undefined,
      }))
  }, [allGroupsForPicker, existingGroupIds])

  const { mutate: addMember, isPending } = accessClient.useMutation('post', '/groups/{group_id}/members')

  const handleClose = () => {
    reset()
    onClose()
  }

  const onFormSubmit = (data: AddToGroupFormData) => {
    const group = availableGroups.find((g) => g.value === data.groupId)
    addMember(
      {
        params: { path: { group_id: data.groupId } },
        body: { user_id: userId },
      },
      {
        onSuccess: () => {
          showSuccess({
            title: 'Added to group',
            description: `User has been added to group "${group?.label ?? data.groupId}".`,
          })
          handleClose()
          onSuccess()
        },
        onError: handleError({ title: 'Failed to add to group' }),
      }
    )
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title="Add to group" />
      <ModalBody>
        <Form id="add-to-group-form" onSubmit={handleSubmit(onFormSubmit)}>
          <FormGroup label="Group" fieldId="add-to-group-select" isRequired>
            <Controller
              name="groupId"
              control={control}
              render={({ field, fieldState }) => (
                <>
                  <TypeaheadSelect
                    id="add-to-group-select"
                    ariaLabel="Select a group"
                    options={availableGroups}
                    selected={field.value}
                    onChange={field.onChange}
                    placeholder="Search for a group..."
                    hasError={!!fieldState.error}
                  />
                  {fieldState.error && (
                    <FormHelperText>
                      <HelperText>
                        <HelperTextItem variant="error">{fieldState.error.message}</HelperTextItem>
                      </HelperText>
                    </FormHelperText>
                  )}
                </>
              )}
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" type="submit" form="add-to-group-form" isDisabled={isPending} isLoading={isPending}>
          Add
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}

function applyGroupFilters<T extends { name: string; description?: string | null }>(
  groups: T[],
  filters: { key: string; value: unknown }[]
): T[] {
  let result = groups
  const nameFilter = filters.find((f) => f.key === 'name')
  if (nameFilter) {
    const term = String(nameFilter.value).toLowerCase()
    result = result.filter((g) => g.name.toLowerCase().includes(term))
  }
  const descFilter = filters.find((f) => f.key === 'description')
  if (descFilter) {
    const term = String(descFilter.value).toLowerCase()
    result = result.filter((g) => (g.description ?? '').toLowerCase().includes(term))
  }
  return result
}

function getGroupActions(
  group: Group,
  onRemove: (g: GroupInfo) => void,
  permissions: ReturnType<typeof useGroupPermissions>
): IAction[] {
  if (group.name === BUILTIN_AUTHENTICATED_GROUP_NAME) return []
  return [
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Remove</IconLabel>,
      isAriaDisabled: !permissions.canManageMembers,
      tooltipProps: permissions.canManageMembers ? undefined : { content: permissions.tooltips.manageMembers },
      onClick: permissions.canManageMembers ? () => onRemove({ id: group.id, name: group.name }) : undefined,
    },
  ]
}

function removeMemberFromGroup(opts: {
  groupToRemove: GroupInfo | null
  userId: string
  removeMember: (
    params: { params: { path: { group_id: string; user_id: string } } },
    callbacks: Record<string, unknown>
  ) => void
  showAlert: (alert: { title: string; description: string; variant: 'success' | 'error'; autoDismiss: boolean }) => void
  refetch: () => Promise<unknown>
  setGroupToRemove: (g: GroupInfo | null) => void
}) {
  if (!opts.groupToRemove) return
  opts.removeMember(
    { params: { path: { group_id: opts.groupToRemove.id, user_id: opts.userId } } },
    {
      onSuccess: () => {
        opts.showAlert({
          title: 'Removed from group',
          description: `User has been removed from group "${opts.groupToRemove!.name}".`,
          variant: 'success',
          autoDismiss: true,
        })
        detachPromise(opts.refetch())
      },
      onError: (err: unknown) => {
        opts.showAlert({
          title: 'Failed to remove from group',
          description: getErrorMessage(err),
          variant: 'error',
          autoDismiss: true,
        })
      },
      onSettled: () => opts.setGroupToRemove(null),
    }
  )
}

export function UserGroupsPanel({ userId }: Readonly<UserGroupsPanelProps>) {
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [groupToRemove, setGroupToRemove] = useState<GroupInfo | null>(null)
  const { filters, setAllFilters, clearAllFilters } = useFilterState()
  const groupPermissions = useGroupPermissions()
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const { showAlert } = useAlerts()

  const handleFilterChange = (newFilters: typeof filters) => {
    setAllFilters(newFilters)
    setPage(1)
  }
  const handlePerPageChange = (newPerPage: number) => {
    setPerPage(newPerPage)
    setPage(1)
  }
  const query = accessClient.useQuery('get', '/users/{user_id}/groups', {
    params: { path: { user_id: userId } },
  })

  const groups = useMemo(() => query.data?.resources ?? [], [query.data])

  const filteredGroups = useMemo(() => applyGroupFilters(groups, filters), [groups, filters])

  const paginatedGroups = useMemo(() => {
    const start = (page - 1) * perPage
    return filteredGroups.slice(start, start + perPage)
  }, [filteredGroups, page, perPage])

  const { mutate: removeMember } = accessClient.useMutation('delete', '/groups/{group_id}/members/{user_id}')
  const handleRemove = () =>
    removeMemberFromGroup({
      groupToRemove,
      userId,
      removeMember,
      showAlert,
      refetch: query.refetch,
      setGroupToRemove,
    })

  const queryState = useQueryState(query, {
    title: 'Error loading groups',
    onRetry: () => detachPromise(query.refetch()),
  })
  if (queryState) return queryState

  if (groups.length === 0) {
    return (
      <>
        <NxEmptyStateNoData
          title="No groups"
          description="This user is not a member of any groups."
          buttonText="Add to group"
          addData={groupPermissions.canManageMembers ? () => setAddModalOpen(true) : undefined}
        />
        <AddToGroupModal
          userId={userId}
          isOpen={addModalOpen}
          onClose={() => setAddModalOpen(false)}
          onSuccess={() => detachPromise(query.refetch())}
          existingGroupIds={[]}
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
                isDisabled={!groupPermissions.canManageMembers}
                content={groupPermissions.tooltips.manageMembers}
              >
                <Button
                  variant="primary"
                  icon={<RhUiAddIcon />}
                  isAriaDisabled={!groupPermissions.canManageMembers}
                  onClick={groupPermissions.canManageMembers ? () => setAddModalOpen(true) : undefined}
                >
                  Add to group
                </Button>
              </DisabledWithTooltip>
            </FlexItem>
          </Flex>
        </StackItem>

        {filteredGroups.length === 0 ? (
          <SynPageBody isCentered>
            <NxEmptyStateFilter
              clearAllFilters={() => {
                clearAllFilters()
                setPage(1)
              }}
            />
          </SynPageBody>
        ) : (
          <NxScrollableTableContainer
            caption="User groups table"
            footer={{
              page,
              perPage,
              total: filteredGroups.length,
              hasNext: page * perPage < filteredGroups.length,
              onPrev: () => setPage((p) => Math.max(1, p - 1)),
              onNext: () => setPage((p) => p + 1),
              onPerPageChange: handlePerPageChange,
            }}
          >
            <Thead>
              <Tr>
                <Th>Name</Th>
                <Th>Description</Th>
                <Th>Source</Th>
                <Th screenReaderText="Actions" />
              </Tr>
            </Thead>
            <Tbody>
              {paginatedGroups.map((group) => (
                <Tr key={group.id}>
                  <Td dataLabel="Name">
                    {group.id ? (
                      <LinkCell href={getGroupDetailPath(group.id)}>
                        <Truncate content={group.name} />
                      </LinkCell>
                    ) : (
                      <Truncate content={group.name} />
                    )}
                    {group.name === BUILTIN_AUTHENTICATED_GROUP_NAME && (
                      <>
                        {' '}
                        <NxLabel color="grey">All users</NxLabel>
                      </>
                    )}
                  </Td>
                  <Td dataLabel="Description">
                    <Truncate content={group.description ?? ''} />
                  </Td>
                  <Td dataLabel="Source">
                    <MembershipSourceLabels sources={getMembershipSources(group)} />
                  </Td>
                  <Td isActionCell>
                    {group.name !== BUILTIN_AUTHENTICATED_GROUP_NAME && (
                      <ActionsColumn items={getGroupActions(group as Group, setGroupToRemove, groupPermissions)} />
                    )}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </NxScrollableTableContainer>
        )}
      </SynPanelContentStack>

      <AddToGroupModal
        userId={userId}
        isOpen={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={() => detachPromise(query.refetch())}
        existingGroupIds={groups.flatMap((g) => (g.id ? [g.id] : []))}
      />

      <NxConfirmationDialog
        isOpen={!!groupToRemove}
        onClose={() => setGroupToRemove(null)}
        onConfirm={handleRemove}
        title="Remove from group?"
        confirmLabel="Remove"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        This removes the user from group <strong>{groupToRemove?.name}</strong>. They will lose any permissions granted
        through this group membership.
      </NxConfirmationDialog>
    </>
  )
}
