import {
  Button,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  Flex,
  FlexItem,
  Switch,
  Truncate,
} from '@patternfly/react-core'
import { RhUiBanIcon, RhUiEditIcon, RhUiSecurityIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { ActionsColumn, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import type { IAction } from '@patternfly/react-table'
import type { IdentityProvidersAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useLayoutEffect, useMemo, useState } from 'react'

import { AppRoute } from '../../../app/AppRoute'
import { adminClient, identityProvidersClient } from '../../../client'
import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import { DisabledWithTooltip } from '../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../components/IconLabel'
import { SynListPanelTable, SynListPanelToolbar, SynListPanelView } from '../../../components/panels/list/SynListPanel'
import { ProviderIcon } from '../../../components/ProviderIcon'
import { SynLink } from '../../../components/SynLink'
import { useCursorPagination } from '../../../hooks/useCursorPagination'
import { useDeleteAction } from '../../../hooks/useDeleteAction'
import { useDialogState } from '../../../hooks/useDialogState'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'
import { useTableSort } from '../../../hooks/useTableSort'
import { useAlerts } from '../../../providers/alerts'
import type { FilterFieldDefinition } from '../../../types/filters'
import { detachPromise } from '../../../utils/detachPromise'

import { DisableIdentityProviderDialog } from './DisableIdentityProviderDialog'
import { AAPSetupModal } from './identity-providers/AAPSetupModal'
import { IdentityProviderDeleteDialog } from './identity-providers/IdentityProviderDeleteDialog'
import { getProviderNameFilterDefinition, getProviderStatusFilterDefinition } from './identityProviderFilters'
import { AddProviderButton } from './IdentityProvidersPageToolbar'
import { useIdentityProviderPermissions } from './useIdentityProviderPermissions'
import { useIdentityProviderToggle } from './useIdentityProviderToggle'

const SORT_FIELDS = ['name', 'issuer_url', 'client_id', 'enabled'] as const

type IdentityProvider = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']

function tooltipWhenDenied(allowed: boolean, text: string) {
  return allowed ? undefined : { content: text }
}

function getRowActions(
  provider: IdentityProvider,
  onDelete: (provider: IdentityProvider) => void,
  onRevoke: (provider: IdentityProvider) => void,
  permissions: ReturnType<typeof useIdentityProviderPermissions>,
  onNavigate: (path: string) => void
): IAction[] {
  const { id } = provider
  const canEdit = permissions.canUpdate && !!id
  const canDel = permissions.canDelete && !!id

  return [
    {
      title: <IconLabel icon={<RhUiEditIcon />}>Edit provider</IconLabel>,
      isDisabled: !id,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: tooltipWhenDenied(permissions.canUpdate, permissions.tooltips.update),
      onClick: canEdit
        ? () => onNavigate(AppRoute.SystemAdministration.Authentication.EditIdentityProvider.replace(':providerId', id))
        : undefined,
    },
    {
      title: <IconLabel icon={<RhUiEditIcon />}>Edit group mapping</IconLabel>,
      isDisabled: !id,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: tooltipWhenDenied(permissions.canUpdate, permissions.tooltips.editMapping),
      onClick: canEdit
        ? () => onNavigate(AppRoute.SystemAdministration.Authentication.EditGroupMapping.replace(':providerId', id))
        : undefined,
    },
    {
      title: <IconLabel icon={<RhUiBanIcon />}>Revoke tokens</IconLabel>,
      isAriaDisabled: !permissions.canRevoke,
      tooltipProps: tooltipWhenDenied(permissions.canRevoke, permissions.tooltips.revoke),
      onClick: permissions.canRevoke ? () => onRevoke(provider) : undefined,
    },
    { isSeparator: true },
    {
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete</IconLabel>,
      isDisabled: !id,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: tooltipWhenDenied(permissions.canDelete, permissions.tooltips.delete),
      onClick: canDel ? () => onDelete(provider) : undefined,
    },
  ]
}

function providerDetailPath(providerId: string): string {
  return AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(':providerId', providerId)
}

function NoProvidersEmptyState({
  showAapButton,
  onAapSetup,
  permissions,
}: Readonly<{
  showAapButton: boolean
  onAapSetup: () => void
  permissions: ReturnType<typeof useIdentityProviderPermissions>
}>) {
  return (
    <EmptyState headingLevel="h2" titleText="No identity providers configured yet" icon={RhUiSecurityIcon}>
      <EmptyStateBody>
        Configure an external identity provider to enable single sign-on for your organization. OIDC (OpenID Connect) is
        the recommended protocol.
      </EmptyStateBody>
      <EmptyStateFooter>
        <EmptyStateActions>
          <AddProviderButton permissions={permissions} />
          {showAapButton && (
            <DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
              <Button
                variant="secondary"
                isAriaDisabled={!permissions.canCreate}
                onClick={permissions.canCreate ? onAapSetup : undefined}
              >
                Add Ansible Automation Platform
              </Button>
            </DisabledWithTooltip>
          )}
        </EmptyStateActions>
      </EmptyStateFooter>
    </EmptyState>
  )
}

function ProviderRow({
  provider,
  permissions,
  onDelete,
  onRevoke,
  onToggleEnabled,
}: Readonly<{
  provider: IdentityProvider
  permissions: ReturnType<typeof useIdentityProviderPermissions>
  onDelete: (p: IdentityProvider) => void
  onRevoke: (p: IdentityProvider) => void
  onToggleEnabled: (p: IdentityProvider) => void
}>) {
  const navigate = useNavigate()
  return (
    <Tr>
      <Td dataLabel="Name">
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }} flexWrap={{ default: 'nowrap' }}>
          <FlexItem style={{ flexShrink: 0 }}>
            <ProviderIcon name={provider.name ?? ''} idpType={provider.configuration?.idp_type} />
          </FlexItem>
          <FlexItem style={{ minWidth: 0 }}>
            {provider.id ? (
              <SynLink to={providerDetailPath(provider.id)}>
                <Truncate content={provider.name ?? ''} />
              </SynLink>
            ) : (
              <Truncate content={provider.name ?? ''} />
            )}
          </FlexItem>
        </Flex>
      </Td>
      <Td dataLabel="Issuer URL">
        <Truncate content={provider.configuration?.issuer_url ?? ''} />
      </Td>
      <Td dataLabel="Client ID">
        <Truncate content={provider.configuration?.client_id ?? ''} />
      </Td>
      <Td dataLabel="State">
        <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.enable}>
          <Switch
            id={`provider-toggle-${provider.id}`}
            label="Enabled"
            isChecked={provider.enabled}
            aria-disabled={!permissions.canUpdate || undefined}
            onChange={permissions.canUpdate ? () => onToggleEnabled(provider) : undefined}
            aria-label={`Toggle ${provider.name}`}
          />
        </DisabledWithTooltip>
      </Td>
      <Td isActionCell>
        <ActionsColumn
          items={getRowActions(provider, onDelete, onRevoke, permissions, (path) =>
            detachPromise(navigate({ to: path }))
          )}
        />
      </Td>
    </Tr>
  )
}

export type IdentityProvidersHeaderToolbarState = {
  showToolbar: boolean
  showAapButton: boolean
  openAapSetup: () => void
  permissions: ReturnType<typeof useIdentityProviderPermissions>
}

type IdentityProvidersTabProps = {
  /** Lift create actions into Authentication's SynPageHeader (Credentials list pattern). */
  onHeaderToolbarStateChange?: (state: IdentityProvidersHeaderToolbarState | null) => void
}

export function IdentityProvidersTab({ onHeaderToolbarStateChange }: Readonly<IdentityProvidersTabProps>) {
  const [aapSetupOpen, setAapSetupOpen] = useState(false)
  const openAapSetup = useCallback(() => {
    ;(document.activeElement as HTMLElement | null)?.blur?.()
    setAapSetupOpen(true)
  }, [])
  const permissions = useIdentityProviderPermissions()
  const deleteDialog = useDialogState<IdentityProvider>()
  const revokeDialog = useDialogState<IdentityProvider>()
  const { showSuccess } = useAlerts()
  const handleMutationError = useMutationErrorHandler()

  const { cursor, filters, hasActiveFilters, queryParams, handleFilterChange, getFooterProps } = useCursorPagination()

  const filterFieldDefinitions = useMemo<FilterFieldDefinition[]>(
    () => [getProviderNameFilterDefinition(), getProviderStatusFilterDefinition()],
    []
  )

  // Server-side sorting — sort param is sent as a query parameter rather than
  // sorting client-side, since the identity providers API supports cursor pagination.
  const { activeSortIndex, sortDirection, getSortParams } = useTableSort({
    initialSortIndex: 0,
    initialDirection: 'asc',
  })

  const sortParam = useMemo(() => {
    const field = SORT_FIELDS[activeSortIndex] ?? 'name'
    return sortDirection === 'desc' ? `-${field}` : field
  }, [activeSortIndex, sortDirection])

  const finalQueryParams = useMemo(() => ({ ...queryParams, sort: sortParam }), [queryParams, sortParam])

  const query = identityProvidersClient.useQuery('get', '/identity_providers', {
    params: { query: finalQueryParams },
  })

  const providers = query.data?.resources ?? []
  const refetch = useCallback(() => detachPromise(query.refetch()), [query])
  const hasAapProvider = useMemo(
    () => (query.data?.resources ?? []).some((p) => p.configuration?.idp_type === 'aap'),
    [query.data?.resources]
  )

  const { mutate: deleteProvider } = identityProvidersClient.useMutation('delete', '/identity_providers/{provider_id}')

  const { disableDialog, isDisabling, handleToggleEnabled, handleConfirmDisable } = useIdentityProviderToggle(() =>
    detachPromise(query.refetch())
  )

  const handleDelete = useDeleteAction({
    deleteFn: deleteProvider,
    buildParams: (provider: IdentityProvider) => ({
      params: { path: { provider_id: provider.id ?? '' } },
    }),
    entityLabel: 'identity provider',
    getItemName: (provider: IdentityProvider) => provider.name ?? '',
    onSuccess: refetch,
    onSettled: deleteDialog.close,
  })

  const { mutate: revokeIdpTokens } = adminClient.useMutation('post', '/admin/revocation/identity_providers/{idp_name}')

  const handleRevoke = () => {
    if (!revokeDialog.item) return
    const idpName = revokeDialog.item.name ?? ''
    revokeIdpTokens(
      { params: { path: { idp_name: idpName } } },
      {
        onSuccess: (data) => {
          showSuccess({
            title: 'Tokens revoked',
            description: data.message,
          })
        },
        onError: handleMutationError({
          title: 'Failed to revoke tokens',
          context: `Identity provider "${idpName}"`,
        }),
        onSettled: revokeDialog.close,
      }
    )
  }

  const showHeaderToolbar = providers.length > 0 || !!cursor || hasActiveFilters

  useLayoutEffect(() => {
    if (!onHeaderToolbarStateChange) return
    onHeaderToolbarStateChange({
      showToolbar: showHeaderToolbar,
      showAapButton: !hasAapProvider,
      openAapSetup,
      permissions,
    })
  }, [onHeaderToolbarStateChange, showHeaderToolbar, hasAapProvider, openAapSetup, permissions])

  useLayoutEffect(() => {
    return () => onHeaderToolbarStateChange?.(null)
  }, [onHeaderToolbarStateChange])

  return (
    <>
      <SynListPanelView
        isPending={query.isPending}
        isFetching={query.isFetching}
        error={query.error}
        errorTitle="Error loading identity providers"
        onRetry={() => detachPromise(query.refetch())}
        isEmpty={providers.length === 0 && !cursor}
        hasActiveFilters={hasActiveFilters}
        onClearAllFilters={() => handleFilterChange([])}
        noDataState={
          <NoProvidersEmptyState showAapButton={!hasAapProvider} onAapSetup={openAapSetup} permissions={permissions} />
        }
        toolbar={
          showHeaderToolbar ? (
            <SynListPanelToolbar
              filters={filters}
              filterDefinitions={filterFieldDefinitions}
              onFilterChange={handleFilterChange}
            />
          ) : undefined
        }
        body={
          <SynListPanelTable caption="Identity providers table" footer={getFooterProps(query.data)}>
            <Thead>
              <Tr>
                <Th sort={getSortParams(0)}>Name</Th>
                <Th sort={getSortParams(1)}>Issuer URL</Th>
                <Th sort={getSortParams(2)}>Client ID</Th>
                <Th sort={getSortParams(3)}>State</Th>
                <Th screenReaderText="Actions" />
              </Tr>
            </Thead>
            <Tbody>
              {providers.map((provider) => (
                <ProviderRow
                  key={provider.id}
                  provider={provider}
                  permissions={permissions}
                  onDelete={deleteDialog.open}
                  onRevoke={revokeDialog.open}
                  onToggleEnabled={handleToggleEnabled}
                />
              ))}
            </Tbody>
          </SynListPanelTable>
        }
      />
      <IdentityProviderDeleteDialog
        isOpen={deleteDialog.isOpen}
        providerName={deleteDialog.item?.name ?? ''}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
      />
      <DisableIdentityProviderDialog
        provider={disableDialog.item}
        isLoading={isDisabling}
        onConfirm={handleConfirmDisable}
        onClose={disableDialog.close}
      />
      <SynConfirmationDialog
        isOpen={revokeDialog.isOpen}
        onClose={revokeDialog.close}
        onConfirm={handleRevoke}
        title="Revoke identity provider tokens?"
        confirmLabel="Revoke tokens"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        All tokens for users authenticated via <strong>{revokeDialog.item?.name}</strong> will be revoked. Affected
        users will be signed out and must sign in again.
      </SynConfirmationDialog>
      <AAPSetupModal
        isOpen={aapSetupOpen}
        onClose={() => setAapSetupOpen(false)}
        onSuccess={() => detachPromise(query.refetch())}
      />
    </>
  )
}
