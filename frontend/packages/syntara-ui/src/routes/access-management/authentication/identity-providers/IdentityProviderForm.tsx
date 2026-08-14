import { zodResolver } from '@hookform/resolvers/zod'
import {
  Button,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  StackItem,
} from '@patternfly/react-core'
import { RhUiArrowLeftIcon, RhUiSearchIcon, RhUiSyncIcon } from '@patternfly/react-icons'
import { type IdentityProvidersAPI } from '@syntara/contracts'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useState, useCallback } from 'react'
import { useForm } from 'react-hook-form'

import { AppRoute } from '../../../../app/AppRoute'
import {
  breadcrumbsIdentityProviderAdd,
  breadcrumbsIdentityProviderEdit,
  breadcrumbsIdentityProviderFormLoading,
} from '../../../../app/breadcrumbBuilders'
import type { AppBreadcrumbItem } from '../../../../app/breadcrumbs/appBreadcrumbItem'
import { identityProvidersClient, OIDC_REDIRECT_URI } from '../../../../client'
import { NxPage, NxPageBody } from '../../../../components/layout/NxPage'
import { NxPageHeader } from '../../../../components/layout/NxPageHeader'
import { NxPanel } from '../../../../components/layout/NxPanel'
import { NxPageTitle } from '../../../../components/NxPageTitle'
import { useQueryState } from '../../../../components/states/useQueryState'
import { useDirtyFormGuard } from '../../../../hooks/useDirtyFormGuard'
import { useFormMutationErrorHandler } from '../../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../../providers/alerts'
import { getErrorMessage, getErrorStatus, isConflictError } from '../../../../utils/apiErrors'
import { detachPromise } from '../../../../utils/detachPromise'
import { useDocLink } from '../../../../utils/docs/useDocLink'

import { autoSelectClaimMappings } from './claimMappingUtils'
import { IdentityProviderFormFields } from './IdentityProviderFormFields'
import {
  identityProviderDefaults,
  identityProviderAddSchema,
  identityProviderEditSchema,
  type IdentityProviderFormData,
} from './identityProviderFormSchema'
import { IdpTypeKey } from './idpTypePresets'

const PROVIDER_TYPE_OIDC = 'oidc' as const

type IdentityProviderFormProps = {
  mode: 'add' | 'edit'
}

function endpointFields(formData: IdentityProviderFormData) {
  return {
    authorization_endpoint: formData.autoDiscovery ? null : formData.authorizationEndpoint || null,
    token_endpoint: formData.autoDiscovery ? null : formData.tokenEndpoint || null,
    jwks_uri: formData.autoDiscovery ? null : formData.jwksUri || null,
    userinfo_endpoint: formData.autoDiscovery ? null : formData.userinfoEndpoint || null,
    end_session_endpoint: formData.autoDiscovery ? null : formData.endSessionEndpoint || null,
  }
}

function claimMappingPayload(formData: IdentityProviderFormData) {
  return {
    subject: formData.claimMapping.subject,
    email: formData.claimMapping.email,
    username: formData.claimMapping.username,
    first_name: formData.claimMapping.firstName,
    last_name: formData.claimMapping.lastName,
  }
}

function groupMappingFields(formData: IdentityProviderFormData) {
  if (!formData.groupMapping) {
    return {
      group_jmespath_expression: null,
      group_mapping_entries: [],
    }
  }
  return {
    group_jmespath_expression: formData.groupMapping.jmespathExpression,
    group_mapping_entries: (formData.groupMapping.entries ?? []).map((e) => ({
      idp_group_value: e.idpGroupValue,
      mapped_group_id: e.nexusGroupId,
    })),
  }
}

function toCreatePayload(formData: IdentityProviderFormData) {
  return {
    name: formData.name,
    enabled: formData.enabled,
    configuration: {
      provider_type: PROVIDER_TYPE_OIDC,
      idp_type: formData.idpType,
      auto_discovery: formData.autoDiscovery,
      issuer_url: formData.issuerUrl,
      client_id: formData.clientId,
      client_secret: formData.clientSecret,
      redirect_uri: OIDC_REDIRECT_URI,
      scopes: formData.scopes,
      ...endpointFields(formData),
      enable_rp_initiated_logout: formData.enableRpInitiatedLogout,
      claim_mapping: claimMappingPayload(formData),
      ...groupMappingFields(formData),
      allow_all_authenticated: formData.allowAllAuthenticated,
      ...(formData.idpType === IdpTypeKey.AAP ? { aap_role_mapping_enabled: formData.aapRoleMappingEnabled } : {}),
      disable_tls_verify: formData.disableTlsVerify,
    },
  }
}

function toPatchPayload(formData: IdentityProviderFormData) {
  return {
    name: formData.name,
    enabled: formData.enabled,
    configuration: {
      provider_type: PROVIDER_TYPE_OIDC,
      idp_type: formData.idpType,
      auto_discovery: formData.autoDiscovery,
      issuer_url: formData.issuerUrl,
      client_id: formData.clientId,
      ...(formData.clientSecret ? { client_secret: formData.clientSecret } : {}),
      redirect_uri: OIDC_REDIRECT_URI,
      scopes: formData.scopes,
      ...endpointFields(formData),
      enable_rp_initiated_logout: formData.enableRpInitiatedLogout,
      claim_mapping: claimMappingPayload(formData),
      ...groupMappingFields(formData),
      allow_all_authenticated: formData.allowAllAuthenticated,
      ...(formData.idpType === IdpTypeKey.AAP ? { aap_role_mapping_enabled: formData.aapRoleMappingEnabled } : {}),
      disable_tls_verify: formData.disableTlsVerify,
    },
  }
}

type ProviderConfig = IdentityProvidersAPI.components['schemas']['OIDCConfigurationResponse']

function stringOrEmpty(value?: string | null): string {
  return value ?? ''
}

function toClaimMappingValues(cm?: ProviderConfig['claim_mapping']): IdentityProviderFormData['claimMapping'] {
  return {
    subject: cm?.subject ?? 'sub',
    email: cm?.email ?? 'email',
    username: cm?.username ?? 'preferred_username',
    firstName: cm?.first_name ?? 'given_name',
    lastName: cm?.last_name ?? 'family_name',
  }
}

function toGroupMappingValues(config?: ProviderConfig): IdentityProviderFormData['groupMapping'] {
  const entries = config?.group_mapping_entries
  if (!entries?.length && !config?.group_jmespath_expression) return null
  return {
    jmespathExpression: config?.group_jmespath_expression ?? 'groups[*]',
    entries: (entries ?? []).map((e) => ({
      idpGroupValue: e.idp_group_value ?? '',
      nexusGroupId: e.mapped_group_id ?? '',
    })),
  }
}

function toEndpointValues(c?: ProviderConfig) {
  return {
    authorizationEndpoint: stringOrEmpty(c?.authorization_endpoint),
    tokenEndpoint: stringOrEmpty(c?.token_endpoint),
    jwksUri: stringOrEmpty(c?.jwks_uri),
    userinfoEndpoint: stringOrEmpty(c?.userinfo_endpoint),
    endSessionEndpoint: stringOrEmpty(c?.end_session_endpoint),
  }
}

function toFormValues(provider: {
  name?: string
  enabled?: boolean
  configuration?: ProviderConfig
}): IdentityProviderFormData {
  const c = provider.configuration
  return {
    idpType: c?.idp_type ?? 'custom',
    name: stringOrEmpty(provider.name),
    enabled: provider.enabled ?? false,
    autoDiscovery: c?.auto_discovery ?? true,
    issuerUrl: stringOrEmpty(c?.issuer_url),
    clientId: stringOrEmpty(c?.client_id),
    clientSecret: '',
    scopes: c?.scopes ?? 'openid profile email',
    ...toEndpointValues(c),
    enableRpInitiatedLogout: c?.enable_rp_initiated_logout ?? false,
    claimMapping: toClaimMappingValues(c?.claim_mapping),
    groupMapping: toGroupMappingValues(c),
    allowAllAuthenticated: c?.allow_all_authenticated ?? false,
    aapRoleMappingEnabled: c?.aap_role_mapping_enabled ?? false,
    disableTlsVerify: c?.disable_tls_verify ?? false,
  }
}

function mapTestConnectionResult(data: {
  success?: boolean
  message?: string
  claims_supported?: string[] | null
  claim_aliases?: Record<string, string[]> | null
  end_session_endpoint_supported?: boolean
}) {
  return {
    success: data.success ?? false,
    message: data.message ?? 'Unknown result',
    claimsSupported: data.claims_supported,
    claimAliases: data.claim_aliases,
    endSessionEndpointSupported: data.end_session_endpoint_supported ?? false,
  }
}

function identityProviderFormBreadcrumbTrail(
  isEdit: boolean,
  pageTitle: string,
  providerId: string | undefined,
  providerName: string | undefined
): AppBreadcrumbItem[] {
  if (!isEdit) {
    return breadcrumbsIdentityProviderAdd()
  }
  const idpDetailPath = providerId
    ? AppRoute.SystemAdministration.Authentication.IdentityProviderDetail.replace(':providerId', providerId)
    : ''
  if (providerName && idpDetailPath) {
    return breadcrumbsIdentityProviderEdit(providerName, idpDetailPath)
  }
  return breadcrumbsIdentityProviderFormLoading(pageTitle)
}

function ProviderNotFound({ onBack, onRetry }: Readonly<{ onBack: () => void; onRetry: () => void }>) {
  return (
    <NxPage>
      <NxPageTitle segments={['Edit OIDC provider', 'Identity Providers']} />
      <NxPageHeader
        title="Edit OIDC provider"
        breadcrumbs={breadcrumbsIdentityProviderFormLoading('Edit OIDC provider')}
      />
      <StackItem isFilled style={{ minHeight: 0, overflow: 'hidden' }}>
        <NxPanel isFullHeight>
          <EmptyState headingLevel="h2" titleText="Identity provider not found" icon={RhUiSearchIcon} isFullHeight>
            <EmptyStateBody>
              The identity provider you are looking for does not exist or may have been deleted.
            </EmptyStateBody>
            <EmptyStateFooter>
              <EmptyStateActions>
                <Button variant="primary" icon={<RhUiArrowLeftIcon />} onClick={onBack}>
                  Back to identity providers
                </Button>
                <Button variant="link" icon={<RhUiSyncIcon />} onClick={onRetry}>
                  Retry
                </Button>
              </EmptyStateActions>
            </EmptyStateFooter>
          </EmptyState>
        </NxPanel>
      </StackItem>
    </NxPage>
  )
}

/**
 * Add / Edit form for OIDC identity providers.
 *
 * Form state rationale:
 * - Uses react-hook-form with `values` (not just `defaultValues`) for edit mode so that
 *   the form re-syncs when the provider query refetches. `defaultValues` alone would only
 *   populate on first mount, leaving stale data after background refetches.
 * - `discoveredClaims` — cached claim metadata from the last "Test connection" call.
 *   Stored in local state (not the form) because it drives the dropdown options in
 *   `ClaimMappingFields` and should survive form resets. On a successful test, the
 *   `autoSelectClaimMappings` helper also writes best-guess values into the form fields
 *   so the user doesn't have to map claims manually.
 * - `testAlert` — transient success/failure feedback from the test connection call.
 *   Kept separate from the form because it is display-only and should not be submitted.
 */
export function IdentityProviderForm({ mode }: Readonly<IdentityProviderFormProps>) {
  const navigate = useNavigate()
  const identityProvidersDocLink = useDocLink('identityProviders')
  const isEdit = mode === 'edit'
  const pageTitle = isEdit ? 'Edit OIDC provider' : 'Add OIDC provider'
  const submitLabel = isEdit ? 'Save provider' : 'Add provider'

  const { providerId }: { providerId: string } = useParams({ strict: false })

  const providerQuery = identityProvidersClient.useQuery(
    'get',
    '/identity_providers/{provider_id}',
    { params: { path: { provider_id: providerId ?? '' } } },
    { enabled: isEdit && !!providerId, retry: false }
  )

  const { mutate: createProvider, isPending: isCreating } = identityProvidersClient.useMutation(
    'post',
    '/identity_providers'
  )
  const { mutate: patchProvider, isPending: isPatching } = identityProvidersClient.useMutation(
    'patch',
    '/identity_providers/{provider_id}'
  )
  const { mutate: testConnection, isPending: isTesting } = identityProvidersClient.useMutation(
    'post',
    '/identity_providers/test'
  )

  const { showAlert, showSuccess } = useAlerts()
  const [discoveredClaims, setDiscoveredClaims] = useState<{
    claimsSupported?: string[] | null
    claimAliases?: Record<string, string[]> | null
  } | null>(null)

  const providerData = providerQuery.data
  const formValues = providerData ? toFormValues(providerData) : undefined

  const schema = isEdit ? identityProviderEditSchema : identityProviderAddSchema
  const {
    control,
    handleSubmit,
    setError,
    getValues,
    setValue,
    trigger,
    formState: { isDirty },
    reset,
  } = useForm<IdentityProviderFormData>({
    resolver: zodResolver(schema, undefined, { mode: 'sync' }),
    mode: 'onBlur',
    defaultValues: formValues ?? identityProviderDefaults,
    values: isEdit && formValues ? formValues : undefined,
  })
  const handleError = useFormMutationErrorHandler<IdentityProviderFormData>(setError)

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => reset(),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this identity provider. Your changes will be lost if you leave.',
  })

  const navigateBack = useCallback(
    () => detachPromise(navigate({ to: AppRoute.SystemAdministration.Authentication.Root })),
    [navigate]
  )

  const handleFormSubmit = useCallback(
    (formData: IdentityProviderFormData, goToStepById: (id: string) => void) => {
      const context = `Identity provider "${formData.name}"`
      const errorTitle = isEdit ? 'Failed to update identity provider' : 'Failed to add identity provider'

      const onConflict = (error: unknown) => {
        if (isConflictError(error)) {
          setError('name', {
            message: `An identity provider named "${formData.name}" already exists. Choose a different name.`,
          })
          goToStepById('provider-config')
          return
        }
        handleError({ title: errorTitle, context })(error)
      }

      const successTitle = isEdit ? 'Identity provider updated' : 'Identity provider created'
      const onSuccess = () => {
        showSuccess({ title: successTitle })
        dismiss()
        navigateBack()
      }

      if (isEdit && providerId) {
        patchProvider(
          { params: { path: { provider_id: providerId } }, body: toPatchPayload(formData) },
          { onSuccess, onError: onConflict }
        )
      } else {
        createProvider({ body: toCreatePayload(formData) }, { onSuccess, onError: onConflict })
      }
    },
    [isEdit, providerId, setError, handleError, showSuccess, dismiss, navigateBack, patchProvider, createProvider]
  )

  const normalizeAndSubmit = useCallback(
    (goToStepById: (id: string) => void) => {
      const gm = getValues('groupMapping')
      if (gm && !gm.entries) {
        setValue('groupMapping', null)
      }
      detachPromise(handleSubmit((formData) => handleFormSubmit(formData, goToStepById))())
    },
    [getValues, setValue, handleSubmit, handleFormSubmit]
  )

  const onTestConnection = useCallback(async () => {
    // Only validate issuer URL — that's all the test endpoint needs
    const isValid = await trigger('issuerUrl')
    if (!isValid) return

    const formData = getValues()
    const fullPayload = toCreatePayload(formData)
    const payload = {
      ...fullPayload,
      name: fullPayload.name || 'connection-test',
      configuration: { ...fullPayload.configuration, client_secret: undefined },
    }
    testConnection(
      { body: payload },
      {
        onSuccess: (data) => {
          const result = mapTestConnectionResult(data)
          showAlert({
            title: result.success ? 'Connection successful' : 'Connection failed',
            description: result.message,
            variant: result.success ? 'success' : 'danger',
            autoDismiss: true,
          })
          if (result.success && result.endSessionEndpointSupported && !getValues('enableRpInitiatedLogout')) {
            showAlert({
              title: 'Single logout supported',
              description: 'This provider supports single logout. You can enable it in the provider configuration.',
              variant: 'info',
              autoDismiss: true,
            })
          }
          setDiscoveredClaims({ claimsSupported: result.claimsSupported, claimAliases: result.claimAliases })
          if (result.claimsSupported && result.claimAliases) {
            autoSelectClaimMappings(result.claimsSupported, result.claimAliases, getValues('claimMapping'), setValue)
          }
        },
        onError: (error: unknown) => {
          showAlert({
            title: 'Connection failed',
            description: getErrorMessage(error),
            variant: 'danger',
            autoDismiss: true,
          })
        },
      }
    )
  }, [trigger, getValues, setValue, testConnection, showAlert])

  const isSaving = isCreating || isPatching

  const refetchProvider = providerQuery.refetch
  const queryState = useQueryState(providerQuery, {
    title: 'Error loading identity provider',
    onRetry: () => detachPromise(refetchProvider()),
  })
  if (isEdit && getErrorStatus(providerQuery.error) === 404) {
    return <ProviderNotFound onBack={navigateBack} onRetry={() => detachPromise(refetchProvider())} />
  }
  if (isEdit && queryState) {
    return (
      <NxPage>
        <NxPageTitle segments={[pageTitle, 'Identity Providers']} />
        <NxPageHeader title={pageTitle} breadcrumbs={breadcrumbsIdentityProviderFormLoading(pageTitle)} />
        <NxPageBody>
          <NxPanel isFullHeight>{queryState}</NxPanel>
        </NxPageBody>
      </NxPage>
    )
  }

  const idpFormCrumbs = identityProviderFormBreadcrumbTrail(isEdit, pageTitle, providerId, providerData?.name)

  return (
    <NxPage>
      <NxPageTitle segments={[pageTitle, 'Identity Providers']} />
      <NxPageHeader title={pageTitle} docLink={identityProvidersDocLink} breadcrumbs={idpFormCrumbs} />
      <NxPageBody>
        {/* hasNoPadding: PF Wizard applies its own lg padding on __main-body; Panel padding would double it. */}
        <NxPanel isFullHeight isScrollable hasNoPadding>
          <IdentityProviderFormFields
            control={control}
            setValue={setValue}
            trigger={trigger}
            isEdit={isEdit}
            testResult={discoveredClaims}
            onTestConnection={onTestConnection}
            isTesting={isTesting}
            submitLabel={submitLabel}
            isSaving={isSaving}
            onSubmit={normalizeAndSubmit}
            onCancel={navigateBack}
          />
        </NxPanel>
      </NxPageBody>
    </NxPage>
  )
}
