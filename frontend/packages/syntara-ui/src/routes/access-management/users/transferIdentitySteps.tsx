import { Content, ContentVariants, EmptyState, EmptyStateBody, StackItem, Title } from '@patternfly/react-core'
import { PlusCircleIcon, RhUiKeyIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { useCallback, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { flexCenteredBothAxes } from '../../../app/flexCenteredBothAxes'
import { FilterBar } from '../../../components/filters/FilterBar'
import { SynLabel } from '../../../components/labels/SynLabel'
import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'
import { SynEmptyStateFilter } from '../../../components/states/SynEmptyStateFilter'
import { SynLink } from '../../../components/SynLink'
import { DateCell } from '../../../components/table/DateCell'
import type { PaginationFooterProps } from '../../../components/table/PaginationFooter'
import { SynScrollableTableContainer } from '../../../components/table/SynScrollableTableContainer'
import { useTableSort } from '../../../hooks/useTableSort'
import type { FilterFieldDefinition } from '../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import { getUserDetailPath } from '../accessManagementPaths'
import { AUTH_SOURCE_LOCAL } from '../adminConstants'

import type { UserIdentity, UserSummary } from './identityUtils'
import { useLocalFilterState } from './identityUtils'
import styles from './TransferIdentityWizard.module.css'

const USER_FILTER_DEFS: FilterFieldDefinition[] = [
  {
    key: 'username',
    label: 'Username',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by username',
  },
  {
    key: 'email',
    label: 'Email',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by email',
  },
]

const IDENTITY_FILTER_DEFS: FilterFieldDefinition[] = [
  {
    key: 'provider_name',
    label: 'Provider',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by provider',
  },
]

/** Step 1: table of non-builtin users with radio selection, filtering, sorting, and pagination. */
export function SelectUserStep({
  targetUsername,
  users,
  selectedUser,
  usersFilter,
  usersSort,
  footerProps,
  onResetPage,
  onSelect,
}: Readonly<{
  targetUsername: string
  users: UserSummary[]
  selectedUser: UserSummary | null
  usersFilter: ReturnType<typeof useLocalFilterState>
  usersSort: ReturnType<typeof useTableSort>
  footerProps: PaginationFooterProps
  onResetPage: () => void
  onSelect: (user: UserSummary) => void
}>) {
  const hasActiveFilters = usersFilter.filters.length > 0
  const showSelectionUi = users.length > 0 || hasActiveFilters

  return (
    <SynPanelContentStack>
      {showSelectionUi && (
        <>
          <StackItem>
            <Title headingLevel="h2" className={styles.stepTitle}>
              Select a user
            </Title>
            <Content component={ContentVariants.p} className={styles.stepDescription}>
              Choose the user whose federated identity you want to transfer. The selected identity will be moved from
              this user to <strong>{targetUsername}</strong>.
            </Content>
          </StackItem>
          <StackItem className={styles.filterBar}>
            <FilterBar
              fieldDefinitions={USER_FILTER_DEFS}
              filters={usersFilter.filters}
              onFilterChange={(f) => {
                usersFilter.setAllFilters(f)
                onResetPage()
              }}
              showClearAll
              isCompact
            />
          </StackItem>
        </>
      )}
      {!showSelectionUi && (
        <StackItem isFilled style={flexCenteredBothAxes}>
          <EmptyState headingLevel="h4" titleText="No users yet" icon={PlusCircleIcon} variant="sm">
            <EmptyStateBody>
              There must be at least one other user before you can transfer a federated identity.
            </EmptyStateBody>
          </EmptyState>
        </StackItem>
      )}
      {users.length === 0 && hasActiveFilters && (
        <StackItem isFilled style={flexCenteredBothAxes}>
          <SynEmptyStateFilter clearAllFilters={usersFilter.clearAllFilters} />
        </StackItem>
      )}
      {users.length > 0 && (
        <SynScrollableTableContainer caption="Select a user" footer={footerProps} useFixedLayout={false}>
          <Thead>
            <Tr>
              <Th screenReaderText="Select" className="pf-v6-c-table__check" />
              <Th sort={usersSort.getSortParams(0)}>Username</Th>
              <Th sort={usersSort.getSortParams(1)}>Email</Th>
              <Th>Authentication</Th>
            </Tr>
          </Thead>
          <Tbody>
            {users.map((user, index) => {
              const isSelected = selectedUser?.id === user.id
              return (
                <Tr key={user.id} isClickable onRowClick={() => onSelect(user)} isRowSelected={isSelected}>
                  <Td
                    select={{
                      rowIndex: index,
                      onSelect: () => onSelect(user),
                      isSelected,
                      variant: 'radio',
                    }}
                  />
                  <Td dataLabel="Username">
                    <SynLink to={getUserDetailPath(user.id)} onClick={(e) => e.stopPropagation()}>
                      {user.username}
                    </SynLink>
                  </Td>
                  <Td dataLabel="Email">{user.email}</Td>
                  <Td dataLabel="Authentication">
                    {(user.auth_sources ?? [AUTH_SOURCE_LOCAL]).map((source) => (
                      <SynLabel key={source} color={source === AUTH_SOURCE_LOCAL ? 'grey' : 'blue'}>
                        {source}
                      </SynLabel>
                    ))}
                  </Td>
                </Tr>
              )
            })}
          </Tbody>
        </SynScrollableTableContainer>
      )}
    </SynPanelContentStack>
  )
}

/** Step 2: table of the selected user's federated identities with radio selection, filtering, and client-side pagination. */
export function SelectIdentityStep({
  selectedUserDisplayName,
  identities,
  selectedIdentityId,
  identitiesFilter,
  identitiesSort,
  onSelect,
}: Readonly<{
  selectedUserDisplayName: string
  identities: UserIdentity[]
  selectedIdentityId: string | null
  identitiesFilter: ReturnType<typeof useLocalFilterState>
  identitiesSort: ReturnType<typeof useTableSort>
  onSelect: (id: string | null) => void
}>) {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const handlePerPageChange = useCallback((n: number) => {
    setPerPage(n)
    setPage(1)
  }, [])
  const paginatedIdentities = identities.slice((page - 1) * perPage, page * perPage)

  const hasActiveFilters = identitiesFilter.filters.length > 0
  const showSelectionUi = identities.length > 0 || hasActiveFilters

  return (
    <SynPanelContentStack>
      {showSelectionUi && (
        <>
          <StackItem>
            <Title headingLevel="h2" className={styles.stepTitle}>
              Select an identity
            </Title>
            <Content component={ContentVariants.p} className={styles.stepDescription}>
              Choose one of <strong>{selectedUserDisplayName}</strong>&apos;s federated identities to attach to the
              current user. This will log <strong>{selectedUserDisplayName}</strong> out of any pre-existing sessions.
            </Content>
          </StackItem>
          <StackItem className={styles.filterBar}>
            <FilterBar
              fieldDefinitions={IDENTITY_FILTER_DEFS}
              filters={identitiesFilter.filters}
              onFilterChange={(f) => {
                identitiesFilter.setAllFilters(f)
                setPage(1)
              }}
              clearAllFilters={() => {
                identitiesFilter.clearAllFilters()
                setPage(1)
              }}
              showClearAll
              isCompact
            />
          </StackItem>
        </>
      )}
      {identities.length === 0 && hasActiveFilters && (
        <StackItem isFilled style={flexCenteredBothAxes}>
          <SynEmptyStateFilter clearAllFilters={identitiesFilter.clearAllFilters} />
        </StackItem>
      )}
      {!showSelectionUi && (
        <StackItem isFilled style={flexCenteredBothAxes}>
          <EmptyState headingLevel="h4" titleText="No identities yet" icon={RhUiKeyIcon} variant="sm">
            <EmptyStateBody>This user has no federated identities to attach.</EmptyStateBody>
          </EmptyState>
        </StackItem>
      )}
      {identities.length > 0 && (
        <SynScrollableTableContainer
          caption="Select an identity"
          useFixedLayout={false}
          footer={{
            page,
            perPage,
            total: identities.length,
            hasNext: page * perPage < identities.length,
            onPrev: () => setPage((p) => Math.max(1, p - 1)),
            onNext: () => setPage((p) => p + 1),
            onPerPageChange: handlePerPageChange,
          }}
        >
          <Thead>
            <Tr>
              <Th screenReaderText="Select" className="pf-v6-c-table__check" />
              <Th sort={identitiesSort.getSortParams(0)}>Provider</Th>
              <Th sort={identitiesSort.getSortParams(1)}>Subject</Th>
              <Th sort={identitiesSort.getSortParams(2)}>Linked</Th>
            </Tr>
          </Thead>
          <Tbody>
            {paginatedIdentities.map((identity, index) => {
              const isSelected = selectedIdentityId === identity.id
              return (
                <Tr
                  key={identity.id}
                  isClickable
                  isRowSelected={isSelected}
                  onRowClick={() => onSelect(isSelected ? null : identity.id)}
                >
                  <Td
                    select={{
                      rowIndex: index,
                      onSelect: () => onSelect(isSelected ? null : identity.id),
                      isSelected,
                      variant: 'radio',
                    }}
                  />
                  <Td dataLabel="Provider">
                    <SynLink
                      to={AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
                        ':providerId',
                        identity.identity_provider_id
                      ).replace('/:tab?', '')}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {identity.provider_name}
                    </SynLink>
                  </Td>
                  <Td dataLabel="Subject">{identity.subject}</Td>
                  <Td dataLabel="Linked">
                    <DateCell dateString={identity.created_at} />
                  </Td>
                </Tr>
              )
            })}
          </Tbody>
        </SynScrollableTableContainer>
      )}
    </SynPanelContentStack>
  )
}
