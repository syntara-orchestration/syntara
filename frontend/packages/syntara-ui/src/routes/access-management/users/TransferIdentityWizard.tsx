import {
  ActionList,
  ActionListGroup,
  ActionListItem,
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Stack,
  StackItem,
  Title,
  useWizardContext,
  Wizard,
  WizardFooterWrapper,
  WizardStep,
  type WizardStepType,
} from '@patternfly/react-core'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsUserDetailEarlyShell } from '../../../app/breadcrumbBuilders'
import { usersClient } from '../../../client'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { DocLinkButton, SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { NxLink } from '../../../components/NxLink'
import { SynLoadingState } from '../../../components/states/SynLoadingState'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { isValidUUID } from '../../../utils/generateUUID'
import { accessClient } from '../../access/accessClient'
import { DetailPageShell } from '../DetailPageShell'

import type { UserSummary } from './identityUtils'
import { SelectIdentityStep, SelectUserStep } from './transferIdentitySteps'
import styles from './TransferIdentityWizard.module.css'
import { userDisplayName } from './userDisplayName'
import { useIdentitiesData, useUsersPagination } from './useTransferIdentityData'

function getNavigateBackPath(userId: string) {
  return `${AppRoute.AccessManagement.UserDetail.replace(':userId', userId)}/identities`
}

/** Step 1 footer with disabled Back, conditional Next, and a Cancel link. */
function WizardFooterStep1({ isNextDisabled, cancelHref }: Readonly<{ isNextDisabled: boolean; cancelHref: string }>) {
  const { goToNextStep } = useWizardContext()
  return (
    <WizardFooterWrapper>
      <ActionList>
        <ActionListGroup>
          <ActionListItem>
            <Button variant="secondary" isDisabled>
              Back
            </Button>
          </ActionListItem>
          <ActionListItem>
            <Button variant="primary" isDisabled={isNextDisabled} onClick={() => detachPromise(goToNextStep())}>
              Next
            </Button>
          </ActionListItem>
          <ActionListItem>
            <NxLink to={cancelHref}>Cancel</NxLink>
          </ActionListItem>
        </ActionListGroup>
      </ActionList>
    </WizardFooterWrapper>
  )
}

/** Step 2 footer with Back, conditional Attach, and a Cancel link. */
function WizardFooterStep2({
  isAttachDisabled,
  isAttaching,
  onAttach,
  cancelHref,
}: Readonly<{
  isAttachDisabled: boolean
  isAttaching: boolean
  onAttach: () => void
  cancelHref: string
}>) {
  const { goToPrevStep } = useWizardContext()
  return (
    <WizardFooterWrapper>
      <ActionList>
        <ActionListGroup>
          <ActionListItem>
            <Button variant="secondary" onClick={goToPrevStep}>
              Back
            </Button>
          </ActionListItem>
          <ActionListItem>
            <Button variant="primary" onClick={onAttach} isDisabled={isAttachDisabled} isLoading={isAttaching}>
              {isAttaching ? 'Transferring...' : 'Transfer identity'}
            </Button>
          </ActionListItem>
          <ActionListItem>
            <NxLink to={cancelHref}>Cancel</NxLink>
          </ActionListItem>
        </ActionListGroup>
      </ActionList>
    </WizardFooterWrapper>
  )
}

/** Full-page wizard for transferring a federated identity from one user to another. */
export function TransferIdentityWizard() {
  const navigate = useNavigate()
  const { userId }: { userId: string } = useParams({ strict: false })
  const safeUserId = userId ?? ''
  const isValidId = !!userId && isValidUUID(userId)
  const transferIdentityDocLink = useDocLink('transferIdentity')

  const { showSuccess } = useAlerts()
  const handleMutationError = useMutationErrorHandler()

  const [selectedUser, setSelectedUser] = useState<UserSummary | null>(null)
  const [selectedIdentityId, setSelectedIdentityId] = useState<string | null>(null)

  const userQuery = accessClient.useQuery(
    'get',
    '/users/{user_id}',
    { params: { path: { user_id: safeUserId } } },
    { enabled: isValidId }
  )

  const { mutate: attachIdentity, isPending: isAttaching } = usersClient.useMutation(
    'post',
    '/users/{user_id}/identities'
  )

  const {
    sortedUsers,
    usersFilter,
    usersSort,
    footerProps: usersFooterProps,
    resetPage,
    usersQuery,
  } = useUsersPagination(safeUserId)
  const { sortedIdentities, identitiesFilter, identitiesSort, userIdentitiesQuery } = useIdentitiesData(
    selectedUser?.id
  )

  const queryState = useQueryState(userQuery, {
    title: 'Error loading user',
    onRetry: () => detachPromise(userQuery.refetch()),
  })

  const usersQueryState = useQueryState(usersQuery, {
    title: 'Error loading users',
    onRetry: () => detachPromise(usersQuery.refetch()),
  })

  const identitiesQueryState = useQueryState(userIdentitiesQuery, {
    title: 'Error loading identities',
    onRetry: () => detachPromise(userIdentitiesQuery.refetch()),
  })

  const navigateBack = () => detachPromise(navigate({ to: getNavigateBackPath(safeUserId) }))

  const handleSelectUser = (user: UserSummary) => {
    if (selectedUser?.id !== user.id) {
      setSelectedIdentityId(null)
      identitiesFilter.clearAllFilters()
    }
    setSelectedUser(user)
  }

  const handleStepChange = (
    _event: React.MouseEvent<HTMLButtonElement>,
    _currentStep: WizardStepType,
    _prevStep: WizardStepType,
    scope: string
  ) => {
    if (scope === 'back') {
      setSelectedUser(null)
      setSelectedIdentityId(null)
      identitiesFilter.clearAllFilters()
    }
  }

  const handleAttach = () => {
    if (!selectedIdentityId) return
    attachIdentity(
      {
        params: { path: { user_id: safeUserId } },
        body: { identity_id: selectedIdentityId },
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Identity transferred' })
          navigateBack()
        },
        onError: handleMutationError({ title: 'Failed to transfer identity' }),
      }
    )
  }

  if (!isValidId) {
    return (
      <DetailPageShell title="Transfer identity" breadcrumbs={breadcrumbsUserDetailEarlyShell()}>
        <Content component={ContentVariants.p}>Invalid user identifier.</Content>
      </DetailPageShell>
    )
  }

  if (queryState) {
    return (
      <DetailPageShell title="Transfer identity" breadcrumbs={breadcrumbsUserDetailEarlyShell()}>
        {queryState}
      </DetailPageShell>
    )
  }

  const userData = userQuery.data
  if (!userData) return <SynLoadingState />

  const targetUsername = userData.username
  const selectedUserDisplayName = selectedUser ? userDisplayName(selectedUser) || selectedUser.username : ''

  return (
    <SynPage>
      <SynPageTitle segments={[`Transfer identity to ${targetUsername}`, 'Users']} />
      <SynPageHeader
        title={`Transfer identity to ${targetUsername}`}
        titleSlot={
          <Stack>
            <StackItem>
              <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
                <FlexItem>
                  <Title headingLevel="h1">Transfer identity to {targetUsername}</Title>
                </FlexItem>
                <FlexItem>
                  <DocLinkButton href={transferIdentityDocLink} />
                </FlexItem>
              </Flex>
            </StackItem>
            <StackItem>
              <Content component={ContentVariants.p} className={styles.descriptionText}>
                Transfer a federated identity from another user to <strong>{targetUsername}</strong>.
              </Content>
            </StackItem>
          </Stack>
        }
      />
      <SynPageBody>
        <SynPanel isFullHeight hasNoPadding>
          <Wizard onClose={navigateBack} onStepChange={handleStepChange} isVisitRequired height="100%">
            <WizardStep
              name="Select a user"
              id="select-user"
              footer={<WizardFooterStep1 isNextDisabled={!selectedUser} cancelHref={getNavigateBackPath(safeUserId)} />}
            >
              {usersQueryState ?? (
                <SelectUserStep
                  targetUsername={targetUsername}
                  users={sortedUsers}
                  selectedUser={selectedUser}
                  usersFilter={usersFilter}
                  usersSort={usersSort}
                  footerProps={usersFooterProps}
                  onResetPage={resetPage}
                  onSelect={handleSelectUser}
                />
              )}
            </WizardStep>
            <WizardStep
              name="Select an identity"
              id="select-identity"
              isDisabled={!selectedUser}
              footer={
                <WizardFooterStep2
                  isAttachDisabled={!selectedIdentityId}
                  isAttaching={isAttaching}
                  onAttach={handleAttach}
                  cancelHref={getNavigateBackPath(safeUserId)}
                />
              }
            >
              {selectedUser &&
                (identitiesQueryState ?? (
                  <SelectIdentityStep
                    selectedUserDisplayName={selectedUserDisplayName}
                    identities={sortedIdentities}
                    selectedIdentityId={selectedIdentityId}
                    identitiesFilter={identitiesFilter}
                    identitiesSort={identitiesSort}
                    onSelect={setSelectedIdentityId}
                  />
                ))}
            </WizardStep>
          </Wizard>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
