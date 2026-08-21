import {
  Badge,
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  Flex,
  FlexItem,
  Label,
  Tab,
  TabTitleText,
} from '@patternfly/react-core'
import { RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { Group } from '@syntara/contracts'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsGroupDetail, breadcrumbsGroupDetailEarlyShell } from '../../../app/breadcrumbBuilders'
import { NxConfirmationDialog } from '../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { NxListPanel, NxListPanelTabs } from '../../../components/panels/list/NxListPanel'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynKebabMenu } from '../../../components/SynKebabMenu'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { DateCell } from '../../../components/table/DateCell'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useDialogState } from '../../../hooks/useDialogState'
import { useUrlTab } from '../../../hooks/useUrlTab'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { accessClient } from '../../access/accessClient'
import { BUILTIN_AUTHENTICATED_GROUP_NAME } from '../adminConstants'
import { DetailPageShell } from '../DetailPageShell'
import { GroupFormModal } from '../GroupFormModal'
import { RoleAssignmentsPanel } from '../RoleAssignmentsPanel'
import { RolePrincipalType } from '../RoleAssignmentTypes'
import { useGroupPermissions } from '../useGroupPermissions'

import { GroupMembersPanel } from './GroupMembersPanel'
import { GroupNotFoundState } from './GroupNotFoundState'
import { useGroupDetailPermissions } from './useGroupDetailPermissions'

function GroupDetailsTab({ group }: Readonly<{ group: Group }>) {
  return (
    <DescriptionList isHorizontal isAutoColumnWidths>
      <DescriptionListGroup>
        <DescriptionListTerm>Name</DescriptionListTerm>
        <DescriptionListDescription>
          <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
            <FlexItem>{group.name}</FlexItem>
            {group.is_builtin && <Label isCompact>Built-in</Label>}
          </Flex>
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Description</DescriptionListTerm>
        <DescriptionListDescription>{group.description ?? '-'}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Created</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={group.created_at} />
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Updated</DescriptionListTerm>
        <DescriptionListDescription>
          <DateCell dateString={group.updated_at} />
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  )
}

function GroupDetailToolbar({
  permissions,
  onEdit,
  onDelete,
}: Readonly<{
  permissions: ReturnType<typeof useGroupPermissions>
  onEdit: () => void
  onDelete: () => void
}>) {
  return (
    <>
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Button
          variant="primary"
          icon={<RhUiEditIcon />}
          isAriaDisabled={!permissions.canUpdate}
          onClick={permissions.canUpdate ? onEdit : undefined}
        >
          Edit group
        </Button>
      </DisabledWithTooltip>
      <SynKebabMenu
        actions={[
          {
            key: 'delete',
            title: <IconLabel icon={<RhUiTrashIcon />}>Delete group</IconLabel>,
            isDanger: true,
            onClick: permissions.canDelete ? onDelete : undefined,
            isAriaDisabled: !permissions.canDelete,
            tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
          },
        ]}
        aria-label="Group actions"
      />
    </>
  )
}

function GroupTabBar({
  basePath,
  showMembers,
  showAssignments,
  memberCount,
  roleAssignmentCount,
}: Readonly<{
  basePath: string
  showMembers: boolean
  showAssignments: boolean
  memberCount: number
  roleAssignmentCount: number
}>) {
  const validTabs = useMemo(() => {
    const tabs: string[] = ['details']
    if (showMembers) tabs.push('members')
    if (showAssignments) tabs.push('roles')
    return tabs
  }, [showMembers, showAssignments])
  return (
    <NxListPanelTabs basePath={basePath} defaultTab="details" validTabs={validTabs} aria-label="Group details">
      <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
      {showMembers && (
        <Tab
          eventKey="members"
          title={
            <TabTitleText>
              Members <Badge isRead>{memberCount}</Badge>
            </TabTitleText>
          }
        />
      )}
      {showAssignments && (
        <Tab
          eventKey="roles"
          title={
            <TabTitleText>
              Assignments <Badge isRead>{roleAssignmentCount}</Badge>
            </TabTitleText>
          }
        />
      )}
    </NxListPanelTabs>
  )
}

function GroupTabContent({
  group,
  groupId,
  activeTab,
  showMembers,
  showAssignments,
  onMembersChange,
}: Readonly<{
  group: Group
  groupId: string
  activeTab: string
  showMembers: boolean
  showAssignments: boolean
  onMembersChange: () => void
}>) {
  return (
    <>
      {activeTab === 'details' && <GroupDetailsTab group={group} />}
      {activeTab === 'members' && showMembers && (
        <GroupMembersPanel groupId={groupId} onMembershipChange={onMembersChange} />
      )}
      {activeTab === 'roles' && showAssignments && (
        <RoleAssignmentsPanel principalType={RolePrincipalType.GROUP} principalId={groupId} />
      )}
    </>
  )
}

function useGroupQueries(groupId: string | undefined) {
  const groupQuery = accessClient.useQuery(
    'get',
    '/groups/{group_id}',
    { params: { path: { group_id: groupId ?? '' } } },
    { enabled: !!groupId, retry: false }
  )

  const isAuthenticated = groupQuery.data?.name === BUILTIN_AUTHENTICATED_GROUP_NAME

  const membersQuery = accessClient.useQuery(
    'get',
    '/groups/{group_id}/members',
    { params: { path: { group_id: groupId ?? '' } } },
    { enabled: !!groupId && !isAuthenticated }
  )

  const roleAssignmentsQuery = accessClient.useQuery(
    'get',
    '/groups/{group_id}/role_assignments',
    { params: { path: { group_id: groupId ?? '' } } },
    { enabled: !!groupId }
  )

  const membersData = membersQuery.data
  const memberCount = membersData?.total ?? membersData?.resources?.length ?? 0
  const roleAssignmentCount = roleAssignmentsQuery.data?.total ?? roleAssignmentsQuery.data?.resources?.length ?? 0

  return { groupQuery, membersQuery, isAuthenticated, memberCount, roleAssignmentCount }
}

export function GroupDetail() {
  const navigate = useNavigate()
  const groupsDocLink = useDocLink('groups')
  const { groupId }: { groupId: string } = useParams({ strict: false })
  const basePath = AppRoute.AccessManagement.GroupDetail.replace(':groupId', groupId ?? '')
  type GroupTab = 'details' | 'members' | 'roles'
  const [activeTab] = useUrlTab<GroupTab>(basePath)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const deleteDialog = useDialogState<Group>()

  const groupPermissions = useGroupPermissions()
  const { mutate: deleteGroup } = accessClient.useMutation('delete', '/groups/{group_id}')
  const { groupQuery, membersQuery, isAuthenticated, memberCount, roleAssignmentCount } = useGroupQueries(groupId)
  const { canReadMembers, canReadAssignments, isLoading: permissionsLoading } = useGroupDetailPermissions()

  const showMembers = !isAuthenticated && (permissionsLoading || canReadMembers)
  const showAssignments = permissionsLoading || canReadAssignments

  const navigateBack = () => detachPromise(navigate({ to: AppRoute.AccessManagement.Groups }))

  const handleDelete = useDeleteAction({
    deleteFn: deleteGroup,
    buildParams: (group: Group) => ({ params: { path: { group_id: group.id } } }),
    entityLabel: 'group',
    getItemName: (group: Group) => group.name,
    onSuccess: navigateBack,
    onSettled: deleteDialog.close,
  })

  const groupData = groupQuery.data
  const refetchGroup = groupQuery.refetch
  const queryState = useQueryState(groupQuery, {
    title: 'Error loading group',
    onRetry: () => {
      detachPromise(refetchGroup())
    },
  })

  if (groupQuery.error) {
    return (
      <DetailPageShell title="Group Details" breadcrumbs={breadcrumbsGroupDetailEarlyShell()}>
        <GroupNotFoundState
          onBack={navigateBack}
          onRetry={() => {
            detachPromise(refetchGroup())
          }}
        />
      </DetailPageShell>
    )
  }

  if (queryState) {
    return (
      <DetailPageShell title="Group Details" breadcrumbs={breadcrumbsGroupDetailEarlyShell()}>
        {queryState}
      </DetailPageShell>
    )
  }

  if (!groupData) return null

  const groupCrumbs = breadcrumbsGroupDetail(groupData.name, basePath, activeTab)

  return (
    <SynPage>
      <SynPageTitle segments={[groupData.name, 'Groups']} />
      <SynPageHeader
        title={groupData.name}
        docLink={groupsDocLink}
        breadcrumbs={groupCrumbs}
        toolbar={
          !groupData.is_builtin ? (
            <GroupDetailToolbar
              permissions={groupPermissions}
              onEdit={() => setEditModalOpen(true)}
              onDelete={() => deleteDialog.open(groupData as Group)}
            />
          ) : undefined
        }
      />
      <SynPageBody>
        <NxListPanel>
          <GroupTabBar
            basePath={basePath}
            showMembers={showMembers}
            showAssignments={showAssignments}
            memberCount={memberCount}
            roleAssignmentCount={roleAssignmentCount}
          />
          <GroupTabContent
            group={groupData as Group}
            groupId={groupId ?? ''}
            activeTab={activeTab}
            showMembers={showMembers}
            showAssignments={showAssignments}
            onMembersChange={() => {
              detachPromise(membersQuery.refetch())
            }}
          />
        </NxListPanel>
      </SynPageBody>

      <GroupFormModal
        group={groupData as Group}
        isOpen={editModalOpen}
        onClose={() => setEditModalOpen(false)}
        onSuccess={() => {
          detachPromise(groupQuery.refetch())
        }}
      />

      {!groupData.is_builtin && (
        <NxConfirmationDialog
          isOpen={deleteDialog.isOpen}
          onClose={deleteDialog.close}
          onConfirm={() => handleDelete(deleteDialog.item)}
          title="Delete group?"
          confirmLabel="Delete"
          confirmVariant="danger"
          titleIconVariant="warning"
          destructiveAcknowledgement={{
            checkboxId: 'delete-group-detail-ack',
            label: 'I understand this group will be permanently deleted.',
          }}
        >
          The group <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
        </NxConfirmationDialog>
      )}
    </SynPage>
  )
}
