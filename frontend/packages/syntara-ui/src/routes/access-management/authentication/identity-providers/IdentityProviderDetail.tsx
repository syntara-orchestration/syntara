import {
  Badge,
  Button,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  Flex,
  FlexItem,
  Label,
  Switch,
  Tab,
  TabTitleText,
} from '@patternfly/react-core'
import {
  RhUiArrowLeftIcon,
  RhUiBanIcon,
  RhUiEditIcon,
  RhUiSearchIcon,
  RhUiSyncIcon,
  RhUiTrashIcon,
} from '@patternfly/react-icons'
import { type IdentityProvidersAPI } from '@syntara/contracts'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useState, type ReactNode } from 'react'

import { AppRoute } from '../../../../app/AppRoute'
import {
  breadcrumbsIdentityProviderDetail,
  breadcrumbsIdentityProviderDetailEarlyShell,
} from '../../../../app/breadcrumbBuilders'
import { adminClient, identityProvidersClient } from '../../../../client'
import { NxConfirmationDialog } from '../../../../components/dialogs/NxConfirmationDialog'
import { DisabledWithTooltip } from '../../../../components/DisabledWithTooltip'
import { IconLabel } from '../../../../components/IconLabel'
import { NxPage, NxPageBody } from '../../../../components/layout/NxPage'
import { NxPageHeader } from '../../../../components/layout/NxPageHeader'
import { NxPanel } from '../../../../components/layout/NxPanel'
import { NxKebabMenu } from '../../../../components/NxKebabMenu'
import type { KebabAction } from '../../../../components/NxKebabMenu'
import { NxPageTitle } from '../../../../components/NxPageTitle'
import { NxListPanel, NxListPanelTabs } from '../../../../components/panels/list/NxListPanel'
import { ProviderIcon } from '../../../../components/ProviderIcon'
import { useQueryState } from '../../../../components/states/useQueryState'
import { DateCell } from '../../../../components/table/DateCell'
import { useDeleteAction } from '../../../../hooks/useDeleteAction'
import { useDialogState } from '../../../../hooks/useDialogState'
import { useMutationErrorHandler } from '../../../../hooks/useMutationErrorHandler'
import { useUrlTab } from '../../../../hooks/useUrlTab'
import { useAlerts } from '../../../../providers/alerts'
import { getErrorStatus } from '../../../../utils/apiErrors'
import { detachPromise } from '../../../../utils/detachPromise'
import { useDocLink } from '../../../../utils/docs/useDocLink'
import { isValidUUID } from '../../../../utils/generateUUID'
import { DisableIdentityProviderDialog } from '../DisableIdentityProviderDialog'
import { useIdentityProviderPermissions } from '../useIdentityProviderPermissions'
import { useIdentityProviderToggle } from '../useIdentityProviderToggle'

import { GroupMappingTab } from './GroupMappingTab'
import { buildGroupMappingConfig, type GroupMappingConfig } from './groupMappingUtils'
import { IdentityProviderDeleteDialog } from './IdentityProviderDeleteDialog'
import { identityProviderGroupMappingEditPath } from './identityProviderPaths'
import { IdpTypeKey, IDP_TYPE_PRESETS } from './idpTypePresets'

type ProviderData = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']
type ProviderConfig = NonNullable<ProviderData['configuration']>

function identityProviderTypeDisplayLabel(idpType: string | null | undefined): string {
  return idpType ? (IDP_TYPE_PRESETS[idpType]?.label ?? idpType) : 'OIDC'
}

function identityProviderDetailMappingCount(groupMappingConfig: GroupMappingConfig | null): number {
  return groupMappingConfig?.group_mapping_entries?.length ?? 0
}

function DetailField({
  label,
  children,
  'data-testid': testId,
}: Readonly<{ label: string; children: React.ReactNode; 'data-testid'?: string }>) {
  return (
    <DescriptionListGroup data-testid={testId}>
      <DescriptionListTerm>{label}</DescriptionListTerm>
      <DescriptionListDescription>{children}</DescriptionListDescription>
    </DescriptionListGroup>
  )
}

function AapRoleMappingField({ config }: Readonly<{ config: ProviderConfig }>) {
  if (config.idp_type !== IdpTypeKey.AAP) return null
  const enabled = config.aap_role_mapping_enabled ?? false
  return (
    <DetailField label="AAP role mapping" data-testid="aap-role-mapping-field">
      <Label color={enabled ? 'blue' : 'grey'} isCompact>
        {enabled ? 'Enabled' : 'Disabled'}
      </Label>
    </DetailField>
  )
}

function ProviderDetailsContent({ provider }: Readonly<{ provider: ProviderData }>) {
  const config = provider.configuration
  if (!config) return null

  const allowAllAuthenticated = config.allow_all_authenticated ?? false

  return (
    <DescriptionList isHorizontal isCompact>
      <DetailField label="Issuer URL">{config.issuer_url ?? '-'}</DetailField>
      <DetailField label="Client ID">{config.client_id ?? '-'}</DetailField>
      <DetailField label="Scopes">
        <Flex gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
          {(config.scopes ?? '')
            .split(/\s+/)
            .filter(Boolean)
            .map((scope) => (
              <FlexItem key={scope}>
                <Label variant="outline" isCompact>
                  {scope}
                </Label>
              </FlexItem>
            ))}
        </Flex>
      </DetailField>
      <DetailField label="Auto-discovery">
        <Label color={config.auto_discovery ? 'blue' : 'grey'} isCompact>
          {config.auto_discovery ? 'Enabled' : 'Disabled'}
        </Label>
      </DetailField>
      <DetailField label="Allow all authenticated" data-testid="allow-all-authenticated-field">
        <Label color={allowAllAuthenticated ? 'blue' : 'grey'} isCompact>
          {allowAllAuthenticated ? 'Enabled' : 'Disabled'}
        </Label>
      </DetailField>
      <AapRoleMappingField config={config} />
      {!config.auto_discovery && (
        <>
          {config.authorization_endpoint && (
            <DetailField label="Authorization endpoint">{config.authorization_endpoint}</DetailField>
          )}
          {config.token_endpoint && <DetailField label="Token endpoint">{config.token_endpoint}</DetailField>}
          {config.jwks_uri && <DetailField label="JWKS URI">{config.jwks_uri}</DetailField>}
          {config.userinfo_endpoint && <DetailField label="Userinfo endpoint">{config.userinfo_endpoint}</DetailField>}
        </>
      )}
      <DetailField label="Created">
        <DateCell dateString={provider.created_at} />
      </DetailField>
      <DetailField label="Last updated">
        <DateCell dateString={provider.updated_at} />
      </DetailField>
    </DescriptionList>
  )
}

type TabContentProps = {
  activeTab: string
  provider: ProviderData
  providerId: string
  providerConfig?: ProviderConfig
  groupMappingConfig: GroupMappingConfig | null
  readOnly: boolean
}

function TabContent({
  activeTab,
  provider,
  providerId,
  providerConfig,
  groupMappingConfig,
  readOnly,
}: Readonly<TabContentProps>) {
  if (activeTab === GROUP_MAPPING_TAB && providerConfig) {
    return <GroupMappingTab providerId={providerId} groupMapping={groupMappingConfig} readOnly={readOnly} />
  }
  return <ProviderDetailsContent provider={provider} />
}

const GROUP_MAPPING_TAB = 'group-mapping' as const
type TabKey = 'details' | typeof GROUP_MAPPING_TAB

function identityProviderDetailBreadcrumbTrail(provider: ProviderData, idpDetailBasePath: string, activeTab: TabKey) {
  return breadcrumbsIdentityProviderDetail(provider.name ?? 'Identity provider', idpDetailBasePath, activeTab)
}

function IdentityProviderDetailEarlyLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <NxPage>
      <NxPageHeader title="Identity Provider Details" breadcrumbs={breadcrumbsIdentityProviderDetailEarlyShell()} />
      <NxPageBody>
        <NxPanel isFullHeight>{children}</NxPanel>
      </NxPageBody>
    </NxPage>
  )
}

function IdentityProviderDetailTabStrip({
  basePath,
  mappingCount,
}: Readonly<{
  basePath: string
  mappingCount: number
}>) {
  return (
    <NxListPanelTabs
      basePath={basePath}
      defaultTab="details"
      validTabs={['details', GROUP_MAPPING_TAB]}
      aria-label="Identity provider details"
    >
      <Tab eventKey="details" title={<TabTitleText>Details</TabTitleText>} />
      <Tab
        eventKey={GROUP_MAPPING_TAB}
        title={<TabTitleText>Group mapping {mappingCount > 0 && <Badge isRead>{mappingCount}</Badge>}</TabTitleText>}
      />
    </NxListPanelTabs>
  )
}

function IdentityProviderDetailToolbar({
  permissions,
  isEnabled,
  kebabActions,
  onToggle,
  onEdit,
}: Readonly<{
  permissions: ReturnType<typeof useIdentityProviderPermissions>
  isEnabled: boolean
  kebabActions: KebabAction[]
  onToggle: () => void
  onEdit: () => void
}>) {
  return (
    <>
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Switch
          id="provider-detail-toggle"
          label="Enabled"
          isChecked={isEnabled}
          aria-disabled={!permissions.canUpdate || undefined}
          onChange={permissions.canUpdate ? onToggle : undefined}
        />
      </DisabledWithTooltip>
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Button
          variant="primary"
          icon={<RhUiEditIcon />}
          isAriaDisabled={!permissions.canUpdate}
          onClick={permissions.canUpdate ? onEdit : undefined}
        >
          Edit provider
        </Button>
      </DisabledWithTooltip>
      <NxKebabMenu actions={kebabActions} aria-label="Identity provider actions" />
    </>
  )
}

function buildKebabActions(
  idpPermissions: ReturnType<typeof useIdentityProviderPermissions>,
  onEditMapping: () => void,
  onRevoke: () => void,
  onDelete: () => void
): KebabAction[] {
  return [
    {
      key: 'edit-mapping',
      title: <IconLabel icon={<RhUiEditIcon />}>Edit group mapping</IconLabel>,
      isAriaDisabled: !idpPermissions.canUpdate,
      tooltipProps: idpPermissions.canUpdate ? undefined : { content: idpPermissions.tooltips.update },
      onClick: idpPermissions.canUpdate ? onEditMapping : undefined,
    },
    {
      key: 'revoke',
      title: <IconLabel icon={<RhUiBanIcon />}>Revoke tokens</IconLabel>,
      isAriaDisabled: !idpPermissions.canRevoke,
      tooltipProps: idpPermissions.canRevoke ? undefined : { content: idpPermissions.tooltips.revoke },
      onClick: idpPermissions.canRevoke ? onRevoke : undefined,
    },
    { key: 'separator', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete identity provider</IconLabel>,
      isDanger: true,
      isAriaDisabled: !idpPermissions.canDelete,
      tooltipProps: idpPermissions.canDelete ? undefined : { content: idpPermissions.tooltips.delete },
      onClick: idpPermissions.canDelete ? onDelete : undefined,
    },
  ]
}

export function IdentityProviderDetail() {
  const navigate = useNavigate()
  const identityProvidersDocLink = useDocLink('identityProviders')
  const { providerId }: { providerId: string } = useParams({ strict: false })
  const isValidId = !!providerId && isValidUUID(providerId)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const revokeDialog = useDialogState<ProviderData>()
  const idpPermissions = useIdentityProviderPermissions()
  const { showSuccess } = useAlerts()
  const handleMutationError = useMutationErrorHandler()
  const canUpdate = idpPermissions.canUpdate
  const idpDetailBasePath = AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(
    ':providerId',
    providerId ?? ''
  )

  const [activeTab] = useUrlTab<TabKey>(idpDetailBasePath)

  const providerQuery = identityProvidersClient.useQuery(
    'get',
    '/identity_providers/{provider_id}',
    { params: { path: { provider_id: providerId ?? '' } } },
    { enabled: isValidId, retry: false }
  )

  const { mutate: deleteProviderMut } = identityProvidersClient.useMutation(
    'delete',
    '/identity_providers/{provider_id}'
  )

  const navigateBack = () => detachPromise(navigate({ to: AppRoute.SystemAdministration.Authentication.Root }))
  const navigateEdit = () =>
    detachPromise(
      navigate({
        to: AppRoute.SystemAdministration.Authentication.EditIdentityProvider.replace(':providerId', providerId ?? ''),
      })
    )

  const providerData = providerQuery.data
  const refetchProvider = providerQuery.refetch

  const {
    disableDialog,
    isDisabling,
    handleToggleEnabled: handleToggle,
    handleConfirmDisable,
  } = useIdentityProviderToggle(() => detachPromise(refetchProvider()))
  const queryState = useQueryState(providerQuery, {
    title: 'Error loading identity provider',
    onRetry: () => detachPromise(refetchProvider()),
  })

  const handleDelete = useDeleteAction({
    deleteFn: deleteProviderMut,
    buildParams: () => ({ params: { path: { provider_id: providerId ?? '' } } }),
    entityLabel: 'identity provider',
    getItemName: () => providerData?.name ?? '',
    onSuccess: navigateBack,
    onSettled: () => setDeleteDialogOpen(false),
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

  const kebabActions = buildKebabActions(
    idpPermissions,
    () => {
      if (providerId) detachPromise(navigate({ to: identityProviderGroupMappingEditPath(providerId) }))
    },
    () => {
      if (providerData) revokeDialog.open(providerData)
    },
    () => setDeleteDialogOpen(true)
  )

  // Check for 404 specifically — show a domain-specific "not found" empty state
  // with navigation back to the list. Let queryState handle all other errors.
  const is404 = getErrorStatus(providerQuery.error) === 404

  if (is404) {
    return (
      <IdentityProviderDetailEarlyLayout>
        <EmptyState headingLevel="h2" titleText="Identity provider not found" icon={RhUiSearchIcon} isFullHeight>
          <EmptyStateBody>
            The identity provider you are looking for does not exist or may have been deleted.
          </EmptyStateBody>
          <EmptyStateFooter>
            <EmptyStateActions>
              <Button variant="primary" icon={<RhUiArrowLeftIcon />} onClick={navigateBack}>
                Back to identity providers
              </Button>
              <Button variant="link" icon={<RhUiSyncIcon />} onClick={() => detachPromise(refetchProvider())}>
                Retry
              </Button>
            </EmptyStateActions>
          </EmptyStateFooter>
        </EmptyState>
      </IdentityProviderDetailEarlyLayout>
    )
  }

  if (queryState) {
    return <IdentityProviderDetailEarlyLayout>{queryState}</IdentityProviderDetailEarlyLayout>
  }

  if (!providerData) return null

  const idpDetailCrumbs = identityProviderDetailBreadcrumbTrail(providerData, idpDetailBasePath, activeTab)

  const config = providerData.configuration
  const idpType = config?.idp_type
  const idpTypeLabel = identityProviderTypeDisplayLabel(idpType)
  const groupMappingConfig = buildGroupMappingConfig(config)
  const mappingCount = identityProviderDetailMappingCount(groupMappingConfig)

  return (
    <NxPage>
      <NxPageTitle segments={[providerData.name ?? '', 'Identity Providers']} />
      <NxPageHeader
        title={providerData.name ?? ''}
        docLink={identityProvidersDocLink}
        breadcrumbs={idpDetailCrumbs}
        titleLeading={
          <ProviderIcon
            name={providerData.name ?? ''}
            idpType={idpType}
            style={{ fontSize: 'var(--pf-t--global--icon--size--xl)', verticalAlign: 'middle' }}
          />
        }
        titleAddons={
          <FlexItem>
            <Label variant="outline">{idpTypeLabel}</Label>
          </FlexItem>
        }
        toolbar={
          <IdentityProviderDetailToolbar
            permissions={idpPermissions}
            isEnabled={providerData.enabled ?? false}
            kebabActions={kebabActions}
            onToggle={() => handleToggle(providerData)}
            onEdit={navigateEdit}
          />
        }
      />
      <NxPageBody>
        <NxListPanel>
          <IdentityProviderDetailTabStrip basePath={idpDetailBasePath} mappingCount={mappingCount} />
          <TabContent
            activeTab={activeTab}
            provider={providerData}
            providerId={providerId ?? ''}
            providerConfig={config}
            groupMappingConfig={groupMappingConfig}
            readOnly={!canUpdate}
          />
        </NxListPanel>
      </NxPageBody>
      <IdentityProviderDeleteDialog
        isOpen={deleteDialogOpen}
        providerName={providerData.name ?? ''}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={() => handleDelete(providerData)}
      />
      <NxConfirmationDialog
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
      </NxConfirmationDialog>
      <DisableIdentityProviderDialog
        provider={disableDialog.item}
        isLoading={isDisabling}
        onConfirm={handleConfirmDisable}
        onClose={disableDialog.close}
      />
    </NxPage>
  )
}
