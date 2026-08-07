import { zodResolver } from '@hookform/resolvers/zod'
import type { IdentityProvidersAPI } from '@syntara/contracts'
import { useNavigate } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { useCallback, useMemo, useState } from 'react'
import { useFieldArray, useForm, type Control, type UseFormReturn } from 'react-hook-form'

import { breadcrumbsIdentityProviderGroupMappingForm } from '../../../../app/breadcrumbBuilders'
import type { AppBreadcrumbItem } from '../../../../app/breadcrumbs/appBreadcrumbItem'
import { identityProvidersClient } from '../../../../client'
import { useQueryState } from '../../../../components/states/useQueryState'
import { useMutationErrorHandler } from '../../../../hooks/useMutationErrorHandler'
import { useAlerts } from '../../../../providers/alerts'
import { getErrorStatus } from '../../../../utils/apiErrors'
import { detachPromise } from '../../../../utils/detachPromise'
import { isValidUUID } from '../../../../utils/generateUUID'
import { useAllGroups } from '../../../access/useAllGroups'
import { BUILTIN_AUTHENTICATED_GROUP_NAME } from '../../adminConstants'

import type { GroupMappingEditFormValues } from './groupMappingEditFormSchema'
import { groupMappingEditFormSchema } from './groupMappingEditFormSchema'
import {
  buildGroupMappingFormDefaultValues,
  groupMappingFormPageTitle,
  parseGroupMappingFormSearch,
} from './groupMappingFormUtils'
import {
  buildGroupMappingConfig,
  buildSavePayload,
  hasServerMappingEntries,
  processDiscoveredGroups,
  type OIDCConfigurationResponse,
} from './groupMappingUtils'
import { identityProviderDetailBasePath, identityProviderGroupMappingTabPath } from './identityProviderPaths'
import { IDP_TYPE_PRESETS } from './idpTypePresets'
import { useTestSignIn } from './useTestSignIn'

type IdentityProviderRead = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']

export type GroupMappingEditPanelState = {
  signInAlert: { variant: 'success' | 'warning' | 'danger'; message: string } | null
  onDismissSignInAlert: () => void
  control: Control<GroupMappingEditFormValues>
  mappingRows: { rowId: string; index: number }[]
  nexusGroups: ReturnType<typeof useAllGroups>['groups']
  onRemove: (index: number) => void
  onAdd: () => void
  onCreateGroup: (index: number) => void
  onReDiscover: () => void
  isListening: boolean
  defaultExpression: string | null
  idpType?: string | null
  rawClaims: string | null
  createGroupForIndex: number | null
  onCloseCreateGroup: () => void
  onGroupCreated: () => Promise<void>
}

export type UseGroupMappingFormMetadataResult = {
  pageTitle: string
  breadcrumbs: AppBreadcrumbItem[]
  isValidId: boolean
  isNotFound: boolean
  queryState: ReactNode | null
  isReady: boolean
  isAddFlow: boolean
  openDiscoverOnMount: boolean
  providerId: string | undefined
  providerData: IdentityProviderRead | undefined
  config: OIDCConfigurationResponse | undefined
  defaultExpression: string | null
  idpType: string | null | undefined
  groupMappingConfig: ReturnType<typeof buildGroupMappingConfig>
}

export function useGroupMappingFormMetadata(
  providerId: string | undefined,
  search: string
): UseGroupMappingFormMetadataResult {
  const isValidId = !!providerId && isValidUUID(providerId)
  const { isAddFlow, openDiscoverOnMount } = parseGroupMappingFormSearch(search)

  const providerQuery = identityProvidersClient.useQuery(
    'get',
    '/identity_providers/{provider_id}',
    { params: { path: { provider_id: providerId ?? '' } } },
    { enabled: isValidId, retry: false }
  )

  const providerData = providerQuery.data
  const config = providerData?.configuration
  const idpType = config?.idp_type
  const groupMappingConfig = config ? buildGroupMappingConfig(config) : null
  const defaultExpression = idpType ? (IDP_TYPE_PRESETS[idpType]?.groupMappingExpression ?? null) : null
  const pageTitle = groupMappingFormPageTitle(hasServerMappingEntries(groupMappingConfig), isAddFlow)

  const groupMappingTabPath = providerId ? identityProviderGroupMappingTabPath(providerId) : ''
  const detailBasePath = providerId ? identityProviderDetailBasePath(providerId) : ''

  const refetchProvider = providerQuery.refetch
  const queryState = useQueryState(providerQuery, {
    title: 'Error loading identity provider',
    onRetry: () => detachPromise(refetchProvider()),
  })

  const breadcrumbs = useMemo(() => {
    if (!providerData?.name || !providerId) {
      return breadcrumbsIdentityProviderGroupMappingForm(
        'Identity provider',
        detailBasePath,
        groupMappingTabPath,
        pageTitle
      )
    }
    return breadcrumbsIdentityProviderGroupMappingForm(
      providerData.name,
      detailBasePath,
      groupMappingTabPath,
      pageTitle
    )
  }, [providerData, providerId, detailBasePath, groupMappingTabPath, pageTitle])

  return {
    pageTitle,
    breadcrumbs,
    isValidId,
    isNotFound: getErrorStatus(providerQuery.error) === 404,
    queryState,
    isReady: Boolean(providerData && config),
    isAddFlow,
    openDiscoverOnMount,
    providerId,
    providerData,
    config,
    defaultExpression,
    idpType,
    groupMappingConfig,
  }
}

export type UseGroupMappingEditFormArgs = {
  providerId: string
  config: OIDCConfigurationResponse
  defaultExpression: string | null
  groupMappingConfig: ReturnType<typeof buildGroupMappingConfig>
  idpType?: string | null
}

export type UseGroupMappingEditFormResult = {
  form: UseFormReturn<GroupMappingEditFormValues>
  isSaving: boolean
  onSave: () => void
  onCancel: () => void
  openTestSignIn: () => void
  panel: GroupMappingEditPanelState
}

export function useGroupMappingEditForm({
  providerId,
  config,
  defaultExpression,
  groupMappingConfig,
  idpType,
}: UseGroupMappingEditFormArgs): UseGroupMappingEditFormResult {
  const navigate = useNavigate()
  const defaultValues = useMemo(
    () => buildGroupMappingFormDefaultValues(groupMappingConfig, defaultExpression),
    [groupMappingConfig, defaultExpression]
  )

  const form = useForm<GroupMappingEditFormValues>({
    resolver: zodResolver(groupMappingEditFormSchema),
    defaultValues,
    mode: 'onSubmit',
  })

  const { fields, append, remove, replace } = useFieldArray({
    control: form.control,
    name: 'entries',
  })

  const mappingRows = useMemo(() => fields.map((field, index) => ({ rowId: field.id, index })), [fields])

  const [signInAlert, setSignInAlert] = useState<{ variant: 'success' | 'warning' | 'danger'; message: string } | null>(
    null
  )
  const [rawClaims, setRawClaims] = useState<string | null>(null)
  const [createGroupForIndex, setCreateGroupForIndex] = useState<number | null>(null)

  const { showSuccess } = useAlerts()
  const handleMutationError = useMutationErrorHandler()

  const { mutate: patchProvider, isPending: isSaving } = identityProvidersClient.useMutation(
    'patch',
    '/identity_providers/{provider_id}'
  )

  const { groups: allGroupsRaw, refetch: refetchGroups } = useAllGroups()
  const nexusGroups = useMemo(
    () => allGroupsRaw.filter((g) => g.name !== BUILTIN_AUTHENTICATED_GROUP_NAME),
    [allGroupsRaw]
  )

  const handleTestResult = useCallback(
    (claims: Record<string, unknown>) => {
      setRawClaims(JSON.stringify(claims, null, 2))
      const currentEntries = form.getValues('entries')
      const result = processDiscoveredGroups(claims, form.getValues('expression'), currentEntries, nexusGroups)
      replace(result.newEntries)
      setSignInAlert({ variant: result.variant, message: result.message })
    },
    [form, nexusGroups, replace]
  )

  const handleTestError = useCallback(() => {
    setSignInAlert({
      variant: 'danger',
      message: 'Could not connect to the identity provider. Verify the provider is reachable and try again.',
    })
  }, [])

  const { openTestSignIn, isListening } = useTestSignIn({
    providerId,
    onResult: handleTestResult,
    onError: handleTestError,
  })

  const navigateToTab = useCallback(() => {
    detachPromise(navigate({ to: identityProviderGroupMappingTabPath(providerId) }))
  }, [navigate, providerId])

  const handleSave = form.handleSubmit((values) => {
    patchProvider(
      {
        params: { path: { provider_id: providerId } },
        body: buildSavePayload(config, values.expression, values.entries),
      },
      {
        onSuccess: () => {
          showSuccess({ title: 'Group mapping saved' })
          navigateToTab()
        },
        onError: handleMutationError({ title: 'Failed to save group mapping' }),
      }
    )
  })

  const handleGroupCreated = useCallback(async () => {
    try {
      const result = await refetchGroups()
      const newGroups = result.data ?? []
      const index = createGroupForIndex
      const entry = index !== null ? form.getValues(`entries.${index}`) : undefined
      if (entry && index !== null && newGroups.length > 0) {
        const newest = [...newGroups].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0]
        if (newest?.id) form.setValue(`entries.${index}.nexusGroupId`, newest.id, { shouldDirty: true })
      }
    } finally {
      setCreateGroupForIndex(null)
    }
  }, [refetchGroups, createGroupForIndex, form])

  const panel: GroupMappingEditPanelState = {
    signInAlert,
    onDismissSignInAlert: () => setSignInAlert(null),
    control: form.control,
    mappingRows,
    nexusGroups,
    onRemove: remove,
    onAdd: () => append({ idpGroupValue: '', nexusGroupId: '' }),
    onCreateGroup: setCreateGroupForIndex,
    onReDiscover: openTestSignIn,
    isListening,
    defaultExpression,
    idpType,
    rawClaims,
    createGroupForIndex,
    onCloseCreateGroup: () => setCreateGroupForIndex(null),
    onGroupCreated: handleGroupCreated,
  }

  return {
    form,
    isSaving,
    onSave: handleSave,
    onCancel: navigateToTab,
    openTestSignIn,
    panel,
  }
}
