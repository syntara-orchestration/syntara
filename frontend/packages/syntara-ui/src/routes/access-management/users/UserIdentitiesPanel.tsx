import { Button, EmptyState, EmptyStateBody, Flex, FlexItem, StackItem, Truncate } from '@patternfly/react-core'
import { RhUiConnectedIcon, RhUiDisconnectedIcon, RhUiKeyIcon, RhUiLinkIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IdentityProvidersAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { resolveLinkError } from '../../../app/authErrorMessages'
import { flexCenteredBothAxes } from '../../../app/flexCenteredBothAxes'
import type { AuthProvider } from '../../../app/useAuthProviders'
import { useAuthProviders } from '../../../app/useAuthProviders'
import { OIDC_AUTHORIZE_PATH, identityProvidersClient, usersClient } from '../../../client'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { FilterBar } from '../../../components/filters/FilterBar'
import { NxLabel } from '../../../components/labels/NxLabel'
import { SynPanelContentStack } from '../../../components/layout/SynPanelContentStack'
import { NxLink } from '../../../components/NxLink'
import { ProviderIcon } from '../../../components/ProviderIcon'
import { NxEmptyStateFilter } from '../../../components/states/NxEmptyStateFilter'
import { NxLoadingState } from '../../../components/states/NxLoadingState'
import { useQueryState } from '../../../components/states/useQueryState'
import { DateCell } from '../../../components/table/DateCell'
import { NxScrollableTableContainer } from '../../../components/table/NxScrollableTableContainer'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useTableSort } from '../../../hooks/useTableSort'
import { useAlerts, type AlertConfig } from '../../../providers/alerts'
import type { FilterConfig, FilterFieldDefinition } from '../../../types/filters'
import { FilterOperatorEnum, FilterTypeEnum } from '../../../types/filters'
import { detachPromise } from '../../../utils/detachPromise'

import { IdentityActionsKebab, IdentityDialogs, type ConvertProviderInfo } from './IdentityDialogs'
import type { UserIdentity } from './identityUtils'
import { applyLocalFilters, useLocalFilterState } from './identityUtils'
import { useUserIdentityPermissions } from './useUserIdentityPermissions'

type IdentityProvider = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']

type IdentityTableRow =
  | { kind: 'connected'; identity: UserIdentity }
  | { kind: 'disconnected'; provider: AuthProvider; issuerUrl: string }

function getIdentitySortKey(sortIndex: number, row: IdentityTableRow): string {
  if (row.kind === 'connected') {
    const keys = [
      row.identity.provider_name ?? '',
      '0',
      row.identity.issuer,
      row.identity.created_at,
      row.identity.last_used_at ?? '',
    ]
    return keys[sortIndex] ?? ''
  }
  const keys = [row.provider.name, '1', row.issuerUrl, '', '']
  return keys[sortIndex] ?? ''
}

const identityFilterDefs: FilterFieldDefinition[] = [
  {
    key: 'provider_name',
    label: 'Provider',
    type: FilterTypeEnum.TEXT,
    operators: [FilterOperatorEnum.CONTAINS],
    defaultOperator: FilterOperatorEnum.CONTAINS,
    placeholder: 'Filter by provider',
  },
]

function useLinkError(showAlert: (config: AlertConfig) => void) {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const error = params.get('link_error')
    if (error) {
      const url = new URL(window.location.href)
      url.searchParams.delete('link_error')
      window.history.replaceState({}, '', url.toString())
      showAlert({ title: 'Failed to link identity', description: resolveLinkError(error), variant: 'danger' })
    }
  }, [showAlert])
}

function ProviderLink({ name, providerId }: { name: string; providerId: string }) {
  return (
    <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }}>
      <FlexItem>
        <ProviderIcon name={name} />
      </FlexItem>
      <FlexItem>
        <NxLink
          to={AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
            ':providerId',
            providerId
          ).replace('/:tab?', '')}
        >
          {name}
        </NxLink>
      </FlexItem>
    </Flex>
  )
}

type IdentityConnectionStatus = 'connected' | 'not_connected'

const identityConnectionStatusMap: Record<IdentityConnectionStatus, 'success' | undefined> = {
  connected: 'success',
  not_connected: undefined,
}

const identityConnectionStatusIcons: Record<IdentityConnectionStatus, React.ComponentType<{ className?: string }>> = {
  connected: RhUiConnectedIcon,
  not_connected: RhUiDisconnectedIcon,
}

const identityConnectionStatusLabels: Record<IdentityConnectionStatus, string> = {
  connected: 'Connected',
  not_connected: 'Not connected',
}

function IdentityConnectionStatusLabel({ status }: Readonly<{ status: IdentityConnectionStatus }>) {
  const Icon = identityConnectionStatusIcons[status]
  const labelStatus = identityConnectionStatusMap[status]
  return (
    <NxLabel variant="outline" status={labelStatus} icon={<Icon />}>
      {identityConnectionStatusLabels[status]}
    </NxLabel>
  )
}

function ConnectedIdentityRow({
  identity,
  isLastIdentity,
  isDetaching,
  onDisconnect,
  canDetach,
  detachTooltip,
}: {
  identity: UserIdentity
  isLastIdentity: boolean
  isDetaching: boolean
  onDisconnect: () => void
  canDetach: boolean
  detachTooltip: string
}) {
  return (
    <Tr>
      <Td dataLabel="Provider">
        <ProviderLink name={identity.provider_name ?? ''} providerId={identity.identity_provider_id} />
      </Td>
      <Td dataLabel="Status">
        <IdentityConnectionStatusLabel status="connected" />
      </Td>
      <Td dataLabel="Issuer URL">
        <Truncate content={identity.issuer} />
      </Td>
      <Td dataLabel="Linked">
        <DateCell dateString={identity.created_at} />
      </Td>
      <Td dataLabel="Last authenticated">
        <DateCell dateString={identity.last_used_at} />
      </Td>
      <Td isActionCell>
        <IdentityActionsKebab
          kind="connected"
          isLastIdentity={isLastIdentity}
          isDetaching={isDetaching}
          onDisconnect={onDisconnect}
          canDetach={canDetach}
          detachTooltip={detachTooltip}
        />
      </Td>
    </Tr>
  )
}

function DisconnectedIdentityRow({
  provider,
  issuerUrl,
  isSelf,
  isLocalUser,
  onConvert,
}: {
  provider: AuthProvider
  issuerUrl: string
  isSelf: boolean
  isLocalUser: boolean
  onConvert: (info: ConvertProviderInfo) => void
}) {
  const authorizeUrl = `${OIDC_AUTHORIZE_PATH}?provider_id=${encodeURIComponent(provider.id)}&flow=link&redirect_to=${encodeURIComponent(globalThis.location.pathname)}`
  return (
    <Tr>
      <Td dataLabel="Provider">
        <ProviderLink name={provider.name} providerId={provider.id} />
      </Td>
      <Td dataLabel="Status">
        <IdentityConnectionStatusLabel status="not_connected" />
      </Td>
      <Td dataLabel="Issuer URL">
        <Truncate content={issuerUrl} />
      </Td>
      <Td dataLabel="Linked">-</Td>
      <Td dataLabel="Last authenticated">-</Td>
      <Td isActionCell>
        <IdentityActionsKebab
          kind="disconnected"
          isSelf={isSelf}
          isLocalUser={isLocalUser}
          providerName={provider.name}
          authorizeUrl={authorizeUrl}
          onConvert={onConvert}
        />
      </Td>
    </Tr>
  )
}

function useIdentityPagination() {
  const identitiesFilter = useLocalFilterState()
  const { setAllFilters } = identitiesFilter
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const handlePerPageChange = useCallback((n: number) => {
    setPerPage(n)
    setPage(1)
  }, [])
  const handleFilterChange = useCallback(
    (f: FilterConfig[]) => {
      setAllFilters(f)
      setPage(1)
    },
    [setAllFilters]
  )
  return { identitiesFilter, page, setPage, perPage, handlePerPageChange, handleFilterChange }
}

function IdentityDialogsWrapper({
  identityToDetach,
  isDetaching,
  confirmDetach,
  onCancelDetach,
  convertProvider,
  onCloseConvert,
}: {
  identityToDetach: UserIdentity | null
  isDetaching: boolean
  confirmDetach: () => void
  onCancelDetach: () => void
  convertProvider: ConvertProviderInfo | null
  onCloseConvert: () => void
}) {
  return (
    <IdentityDialogs
      identityToDetach={identityToDetach}
      isDetaching={isDetaching}
      onConfirmDetach={confirmDetach}
      onCancelDetach={onCancelDetach}
      convertProvider={convertProvider}
      onCloseConvert={onCloseConvert}
      onConfirmConvert={() => {
        if (convertProvider) {
          globalThis.location.href = convertProvider.authorizeUrl
        }
      }}
    />
  )
}

function buildIdentityRows(
  identities: UserIdentity[],
  unlinkedProviders: AuthProvider[],
  fullProviders: IdentityProvider[]
): IdentityTableRow[] {
  const connected: IdentityTableRow[] = identities.map((identity) => ({ kind: 'connected', identity }))
  const disconnected: IdentityTableRow[] = unlinkedProviders.map((provider) => {
    const fullProvider = fullProviders.find((p) => p.id === provider.id)
    return { kind: 'disconnected', provider, issuerUrl: fullProvider?.configuration?.issuer_url ?? '' }
  })
  return [...connected, ...disconnected]
}

function getIdentityFilterValue(row: IdentityTableRow, key: string): string {
  if (key === 'provider_name') {
    return row.kind === 'connected' ? (row.identity.provider_name ?? '') : row.provider.name
  }
  return ''
}

type UserIdentitiesPanelProps = {
  userId: string
  currentUserId?: string
  /** Built-in users (e.g. admin) can never link identity providers. */
  isBuiltinUser?: boolean
  /** Local users see a conversion warning before linking an identity provider. */
  isLocalUser?: boolean
  /**
   * Whether this user can sign in with a local password (not inferred here — callers must supply).
   * Used so the last linked federated identity cannot be removed when no password fallback exists.
   */
  hasPassword: boolean
}

export function UserIdentitiesPanel({
  userId,
  currentUserId,
  isBuiltinUser = false,
  isLocalUser = false,
  hasPassword,
}: Readonly<UserIdentitiesPanelProps>) {
  const navigate = useNavigate()
  const identityPermissions = useUserIdentityPermissions()
  const { showAlert } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const [identityToDetach, setIdentityToDetach] = useState<UserIdentity | null>(null)
  const [convertProvider, setConvertProvider] = useState<ConvertProviderInfo | null>(null)
  const { identitiesFilter, page, setPage, perPage, handlePerPageChange, handleFilterChange } = useIdentityPagination()
  const { providers, isLoading: isProvidersLoading } = useAuthProviders()
  const isSelf = userId === currentUserId
  useLinkError(showAlert)

  const query = usersClient.useQuery(
    'get',
    '/users/{user_id}/identities',
    { params: { path: { user_id: userId } } },
    { refetchOnWindowFocus: 'always' }
  )

  const identitiesQuery = identityProvidersClient.useQuery('get', '/identity_providers', {})

  const identities = useMemo(() => query.data?.resources ?? [], [query.data])
  const fullProviders = useMemo<IdentityProvider[]>(() => identitiesQuery.data?.resources ?? [], [identitiesQuery.data])

  const { mutate: detachIdentity, isPending: isDetaching } = usersClient.useMutation(
    'delete',
    '/users/{user_id}/identities/{identity_id}'
  )

  const linkedProviderIds = useMemo(() => new Set(identities.map((i) => i.identity_provider_id)), [identities])
  const unlinkedProviders = useMemo(
    () => providers.filter((p) => !linkedProviderIds.has(p.id)),
    [providers, linkedProviderIds]
  )

  const allRows = useMemo(
    () => buildIdentityRows(identities, unlinkedProviders, fullProviders),
    [identities, unlinkedProviders, fullProviders]
  )

  const filteredRows = applyLocalFilters(allRows, identitiesFilter.filters, getIdentityFilterValue)

  const { activeSortIndex, getSortParams, sortData } = useTableSort({ initialSortIndex: 1, initialDirection: 'asc' })
  const sortedRows = sortData(filteredRows, (row) => getIdentitySortKey(activeSortIndex, row))

  const queryState = useQueryState(query, {
    title: 'Error loading identities',
    onRetry: () => detachPromise(query.refetch()),
  })
  if (queryState) return queryState

  const confirmDetach = () => {
    if (!identityToDetach) return
    detachIdentity(
      { params: { path: { user_id: userId, identity_id: identityToDetach.id } } },
      {
        onSuccess: () => {
          showAlert({ title: 'Identity disconnected', variant: 'success', autoDismiss: true })
          detachPromise(query.refetch())
        },
        onError: handleMutationError({ title: 'Failed to disconnect identity' }),
        onSettled: () => setIdentityToDetach(null),
      }
    )
  }

  const hasActiveFilters = identitiesFilter.filters.length > 0
  const showTable = identities.length > 0 || (!isBuiltinUser && unlinkedProviders.length > 0) || hasActiveFilters

  const handleTransferIdentity = identityPermissions.canAttach
    ? () => detachPromise(navigate({ to: AppRoute.AccessManagement.TransferIdentity.replace(':userId', userId) }))
    : undefined

  const dialogs = (
    <IdentityDialogsWrapper
      identityToDetach={identityToDetach}
      isDetaching={isDetaching}
      confirmDetach={confirmDetach}
      onCancelDetach={() => setIdentityToDetach(null)}
      convertProvider={convertProvider}
      onCloseConvert={() => setConvertProvider(null)}
    />
  )

  if (isBuiltinUser && identities.length === 0) {
    return (
      <EmptyState headingLevel="h3" titleText="Built-in user" icon={RhUiKeyIcon}>
        <EmptyStateBody>
          The built-in administrator account cannot be linked to external identity providers.
        </EmptyStateBody>
      </EmptyState>
    )
  }

  // Prevent "No identity providers configured" from flashing before useAuthProviders settles.
  if (isProvidersLoading && identities.length === 0) return <NxLoadingState />

  if (!showTable) {
    return (
      <>
        <EmptyState headingLevel="h3" titleText="No identity providers configured" icon={RhUiKeyIcon}>
          <EmptyStateBody>
            There are no identity providers configured. Configure an identity provider to enable federated
            authentication.
          </EmptyStateBody>
        </EmptyState>
        {dialogs}
      </>
    )
  }

  return (
    <SynPanelContentStack>
      <StackItem>
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapMd' }}>
          <FlexItem grow={{ default: 'grow' }}>
            <FilterBar
              fieldDefinitions={identityFilterDefs}
              filters={identitiesFilter.filters}
              onFilterChange={handleFilterChange}
              showClearAll
            />
          </FlexItem>
          {!isBuiltinUser && (
            <FlexItem>
              <DisabledWithTooltip
                isDisabled={!identityPermissions.canAttach}
                content={identityPermissions.tooltips.attach}
              >
                <Button
                  variant="primary"
                  icon={<RhUiLinkIcon />}
                  isAriaDisabled={!identityPermissions.canAttach}
                  onClick={handleTransferIdentity}
                >
                  Transfer identity
                </Button>
              </DisabledWithTooltip>
            </FlexItem>
          )}
        </Flex>
      </StackItem>
      {sortedRows.length === 0 ? (
        <StackItem isFilled style={flexCenteredBothAxes}>
          <NxEmptyStateFilter clearAllFilters={identitiesFilter.clearAllFilters} />
        </StackItem>
      ) : (
        <NxScrollableTableContainer
          caption="User identities table"
          footer={{
            page,
            perPage,
            total: sortedRows.length,
            hasNext: page * perPage < sortedRows.length,
            onPrev: () => setPage((p) => Math.max(1, p - 1)),
            onNext: () => setPage((p) => p + 1),
            onPerPageChange: handlePerPageChange,
          }}
        >
          <Thead>
            <Tr>
              <Th sort={getSortParams(0)}>Provider</Th>
              <Th sort={getSortParams(1)}>Status</Th>
              <Th sort={getSortParams(2)}>Issuer URL</Th>
              <Th sort={getSortParams(3)}>Linked</Th>
              <Th sort={getSortParams(4)}>Last authenticated</Th>
              <Th screenReaderText="Actions" />
            </Tr>
          </Thead>
          <Tbody>
            {sortedRows.slice((page - 1) * perPage, page * perPage).map((row) => {
              if (row.kind === 'connected') {
                return (
                  <ConnectedIdentityRow
                    key={row.identity.id}
                    identity={row.identity}
                    isLastIdentity={identities.length === 1 && !hasPassword}
                    isDetaching={isDetaching}
                    onDisconnect={() => setIdentityToDetach(row.identity)}
                    canDetach={identityPermissions.canDetach}
                    detachTooltip={identityPermissions.tooltips.detach}
                  />
                )
              }
              return (
                <DisconnectedIdentityRow
                  key={`unlinked-${row.provider.id}`}
                  provider={row.provider}
                  issuerUrl={row.issuerUrl}
                  isSelf={isSelf}
                  isLocalUser={isLocalUser}
                  onConvert={setConvertProvider}
                />
              )
            })}
          </Tbody>
        </NxScrollableTableContainer>
      )}
      {dialogs}
    </SynPanelContentStack>
  )
}
