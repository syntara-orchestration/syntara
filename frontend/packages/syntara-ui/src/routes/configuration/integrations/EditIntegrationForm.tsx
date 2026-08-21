import { zodResolver } from '@hookform/resolvers/zod'
import {
  ActionGroup,
  Button,
  Content,
  ContentVariants,
  DescriptionList,
  Divider,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  TextArea,
  TextInput,
  Title,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useRef } from 'react'
import { Controller, useForm, useWatch, type Resolver } from 'react-hook-form'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsIntegrationEdit } from '../../../app/breadcrumbBuilders'
import { integrationsClient } from '../../../client'
import { NxDetail } from '../../../components/details/NxDetail'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { NxErrorState } from '../../../components/states/NxErrorState'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { useDirtyFormGuard } from '../../../hooks/useDirtyFormGuard'
import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { CredentialSelector } from '../../builder/components/CredentialSelector'

import styles from './EditIntegrationForm.module.css'
import type { EditIntegrationFormValues, IntegrationRead } from './editIntegrationFormSchema'
import { buildConfiguration, buildEditSchema, editIntegrationSchema } from './editIntegrationFormSchema'
import { EditSecurityFields } from './EditSecurityFields'
import { ScopeFields } from './form/ScopeFields'
import { integrationHelp } from './integrationFieldHelp'
import {
  CREDENTIAL_REQUIRED_TYPES,
  CREDENTIAL_TYPES_BY_INTEGRATION,
  INTEGRATION_TYPE_LABELS,
  PROVIDER_HINT_LABELS,
  PROVIDERS_HIDING_BASE_URL,
  PROVIDERS_REQUIRING_BASE_URL,
} from './integrationFilters'
import { getProviderHint, isLLMProvider } from './integrationUtils'
import { useEditTestConnection } from './useEditTestConnection'
import { useProjectAssignmentSync } from './useProjectAssignmentSync'

const CREDENTIAL_DESCRIPTION: Record<string, string> = {
  [IntegrationTypeEnum.MCP_SERVER]:
    'This credential is used for tool discovery and connection status checks. MCP servers that do not require authentication can be configured without one.',
  [IntegrationTypeEnum.LLM_PROVIDER]:
    'This credential is used to verify the connection to this integration and perform periodic health checks. Workflow credentials are configured separately in the workflow builder.',
  [IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM]:
    'This credential is used to verify the connection to the Ansible Automation Platform. Workflow credentials are configured separately in the workflow builder.',
}

type FormFieldsProps = Readonly<{
  integration: IntegrationRead
  control: ReturnType<typeof useForm<EditIntegrationFormValues>>['control']
  errors: ReturnType<typeof useForm<EditIntegrationFormValues>>['formState']['errors']
  scope: string
  credentialId: string | null | undefined
  isTesting: boolean
  setValue: ReturnType<typeof useForm<EditIntegrationFormValues>>['setValue']
  onTestConnection: () => void
}>

function EditIntegrationFormFields({
  integration,
  control,
  errors,
  scope,
  credentialId,
  isTesting,
  setValue,
  onTestConnection,
}: FormFieldsProps) {
  const isCredentialRequired = CREDENTIAL_REQUIRED_TYPES.has(integration.integration_type ?? '')
  const isTestDisabled = (isCredentialRequired && !credentialId) || isTesting
  const isAnsibleAutomationPlatform = integration.integration_type === IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM
  const isLLM = isLLMProvider(integration)
  const hideBaseUrl = isLLM && PROVIDERS_HIDING_BASE_URL.has(getProviderHint(integration))

  const credentialDescription =
    CREDENTIAL_DESCRIPTION[integration.integration_type ?? ''] ?? CREDENTIAL_DESCRIPTION[IntegrationTypeEnum.MCP_SERVER]

  return (
    <>
      <Title headingLevel="h2" size="lg">
        Integration details
      </Title>

      <DescriptionList isCompact isHorizontal>
        <NxDetail label="Integration type">
          {INTEGRATION_TYPE_LABELS[integration.integration_type ?? ''] ?? integration.integration_type ?? ''}
        </NxDetail>
        {isLLM && (
          <NxDetail label="Provider type">
            {PROVIDER_HINT_LABELS[getProviderHint(integration)] ?? getProviderHint(integration)}
          </NxDetail>
        )}
      </DescriptionList>

      <FormGroup
        label={isLLM ? 'Name' : 'Server name / ID'}
        isRequired
        fieldId="edit-name"
        labelHelp={isLLM ? integrationHelp.name : integrationHelp.serverName}
      >
        <Controller
          name="name"
          control={control}
          render={({ field }) => (
            <TextInput id="edit-name" isRequired validated={errors.name ? 'error' : 'default'} {...field} />
          )}
        />
        {errors.name && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                {errors.name.message}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </FormGroup>

      <FormGroup label="Description" fieldId="edit-description">
        <Controller
          name="description"
          control={control}
          render={({ field }) => (
            <TextArea
              id="edit-description"
              aria-label="Description"
              resizeOrientation="vertical"
              value={field.value ?? ''}
              onChange={(_event, value) => field.onChange(value)}
              onBlur={field.onBlur}
              name={field.name}
            />
          )}
        />
      </FormGroup>

      {!hideBaseUrl && (
        <FormGroup
          label="API URL"
          isRequired={!isLLM}
          fieldId="edit-base-url"
          labelHelp={isAnsibleAutomationPlatform ? integrationHelp.aapUrl : integrationHelp.apiUrl}
        >
          <Controller
            name="base_url"
            control={control}
            render={({ field }) => (
              <TextInput
                id="edit-base-url"
                isRequired={!isLLM}
                validated={errors.base_url ? 'error' : 'default'}
                {...field}
              />
            )}
          />
          {errors.base_url && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                  {errors.base_url.message}
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
        </FormGroup>
      )}

      <EditSecurityFields control={control} errors={errors} />

      <ScopeFields
        control={control}
        scope={scope}
        scopeName="scope"
        projectIdsName="project_ids"
        idPrefix="edit-integration"
        onScopeChange={(newScope) => {
          if (newScope === 'global') setValue('project_ids', [])
        }}
      />

      <Divider />

      <div>
        <Title headingLevel="h2" size="lg" className={styles.credentialHeading}>
          Connection credential
        </Title>
        <Content component={ContentVariants.p} className={styles.credentialDescription}>
          {credentialDescription}
        </Content>
      </div>

      <Controller
        name="management_credential_id"
        control={control}
        render={({ field }) => (
          <CredentialSelector
            value={field.value ?? undefined}
            onChange={(id) => setValue('management_credential_id', id ?? null)}
            compatibleTypeNames={
              CREDENTIAL_TYPES_BY_INTEGRATION[integration.integration_type ?? IntegrationTypeEnum.MCP_SERVER]
            }
            label="Health check credential"
            fieldId="edit-credential-select"
            isRequired={isCredentialRequired}
            allowCreate
            placeholder="Select a credential"
            labelHelp={integrationHelp.healthCheckCredential}
          />
        )}
      />

      <FormGroup fieldId="test-connection">
        <Button
          variant="secondary"
          onClick={isTestDisabled ? undefined : onTestConnection}
          isLoading={isTesting}
          isAriaDisabled={isTestDisabled}
        >
          Test connection
        </Button>
      </FormGroup>
    </>
  )
}

function EditFormFooter({ isSaving, onCancel }: Readonly<{ isSaving: boolean; onCancel: () => void }>) {
  return (
    <ActionGroup>
      <Button
        variant="primary"
        type="submit"
        form="edit-integration-form"
        isLoading={isSaving}
        isAriaDisabled={isSaving}
      >
        Save integration
      </Button>
      <Button variant="link" onClick={isSaving ? undefined : onCancel} isAriaDisabled={isSaving}>
        Cancel
      </Button>
    </ActionGroup>
  )
}

export function EditIntegrationForm() {
  const { integrationId }: { integrationId: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showAlert } = useAlerts()
  const docLink = useDocLink('integrations')

  const query = integrationsClient.useQuery('get', '/integrations/{integration_id}', {
    params: { path: { integration_id: integrationId ?? '' } },
  })
  const integration = query.data

  const assignmentsQuery = integrationsClient.useQuery(
    'get',
    '/integrations/{integration_id}/projects',
    { params: { path: { integration_id: integrationId ?? '' } } },
    { enabled: integration?.scope === 'project' }
  )
  const initialProjectIds = useMemo(
    () => assignmentsQuery.data?.resources?.map((a) => a.project_id) ?? [],
    [assignmentsQuery.data]
  )
  const initialProjectIdsRef = useRef<string[]>([])

  const { syncAssignments } = useProjectAssignmentSync()

  const detailPath = AppRoute.Configuration.Integrations.Detail.replace(':integrationId', integrationId ?? '')
  const breadcrumbs = breadcrumbsIntegrationEdit(integration?.name ?? 'Integration', detailPath)

  const schema = useMemo(() => {
    if (!integration) return editIntegrationSchema
    const requiresBaseUrl = isLLMProvider(integration)
      ? PROVIDERS_REQUIRING_BASE_URL.has(getProviderHint(integration))
      : true
    return buildEditSchema(requiresBaseUrl)
  }, [integration])

  useEffect(() => {
    const projectIds = integration?.scope === 'project' ? initialProjectIds : []
    initialProjectIdsRef.current = projectIds
  }, [integration, initialProjectIds])

  const formValues = useMemo<EditIntegrationFormValues | undefined>(() => {
    if (!integration) return undefined
    const config = integration.configuration
    const projectIds = integration.scope === 'project' ? initialProjectIds : []
    return {
      name: integration.name ?? '',
      description: integration.description ?? '',
      integration_type: integration.integration_type ?? IntegrationTypeEnum.MCP_SERVER,
      base_url: 'base_url' in config ? String(config.base_url ?? '') : '',
      allow_http: 'allow_http' in config ? Boolean(config.allow_http) : false,
      insecure_skip_tls_verify: 'insecure_skip_tls_verify' in config ? Boolean(config.insecure_skip_tls_verify) : false,
      ca_certificate: 'ca_certificate' in config ? ((config.ca_certificate as string | null) ?? null) : null,
      scope: (integration.scope as 'global' | 'project') ?? 'global',
      project_ids: projectIds,
      management_credential_id: integration.management_credential_id ?? null,
    }
  }, [integration, initialProjectIds])

  // zodResolver + superRefine → ZodEffects type divergence; known @hookform/resolvers limitation.
  const {
    control,
    handleSubmit,
    setError,
    setValue,
    getValues,
    reset,
    formState: { errors, isDirty },
  } = useForm<EditIntegrationFormValues>({
    resolver: zodResolver(schema, undefined, { mode: 'sync' }) as Resolver<EditIntegrationFormValues>,
    defaultValues: {
      name: '',
      description: '',
      integration_type: '',
      base_url: '',
      allow_http: false,
      insecure_skip_tls_verify: false,
      ca_certificate: null,
      scope: 'global',
      project_ids: [],
      management_credential_id: null,
    },
    values: formValues,
    resetOptions: { keepDirtyValues: true },
  })

  const scope = useWatch({ control, name: 'scope' })
  const credentialId = useWatch({ control, name: 'management_credential_id' })

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => reset(),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this integration. Your changes will be lost if you leave.',
  })

  const handleError = useFormMutationErrorHandler<EditIntegrationFormValues>(setError)

  const { mutateAsync: patchIntegration, isPending: isSaving } = integrationsClient.useMutation(
    'patch',
    '/integrations/{integration_id}'
  )

  const { handleTestConnection, isTesting } = useEditTestConnection(integration, getValues)

  function onSubmit(values: EditIntegrationFormValues) {
    if (!integrationId || !integration) return

    const integrationType = integration.integration_type ?? IntegrationTypeEnum.MCP_SERVER

    const body: IntegrationsAPI.components['schemas']['IntegrationUpdate'] = {
      name: values.name,
      description: values.description || null,
      scope: values.scope,
      configuration: buildConfiguration(
        integrationType,
        values,
        isLLMProvider(integration) ? getProviderHint(integration) : undefined
      ),
      management_credential_id: values.management_credential_id,
    }

    detachPromise(
      (async () => {
        try {
          await patchIntegration({ params: { path: { integration_id: integrationId } }, body })
          await queryClient.invalidateQueries({ queryKey: ['get', '/integrations/{integration_id}'] })
          await queryClient.invalidateQueries({ queryKey: ['get', '/integrations/{integration_id}/projects'] })

          let variant: 'success' | 'warning' = 'success'
          let description = `"${values.name}" has been updated.`
          if (values.scope === 'project') {
            const { errors: syncErrors } = await syncAssignments(
              integrationId,
              initialProjectIdsRef.current,
              values.project_ids ?? []
            )
            if (syncErrors.length > 0) {
              variant = 'warning'
              description = `"${values.name}" was updated but some project assignments failed.`
            }
          }
          showAlert({
            title: `Integration updated${variant === 'warning' ? ' with warnings' : ''}`,
            description,
            variant,
            autoDismiss: true,
          })
          dismiss()
          detachPromise(navigate({ to: detailPath }))
        } catch (error: unknown) {
          handleError({ title: 'Failed to update integration', context: `Integration "${values.name}"` })(error)
        }
      })()
    )
  }
  const queryState = useQueryState(query, {
    title: 'Error loading integration',
    onRetry: () => detachPromise(query.refetch()),
  })
  if (!integrationId || queryState) {
    return (
      <SynPage>
        <SynPageTitle segments={['Edit integration', 'Integrations']} />
        <SynPageHeader title="Edit integration" breadcrumbs={breadcrumbs} docLink={docLink} />
        <SynPageBody>
          <SynPanel isFullHeight>
            {queryState ?? <NxErrorState message="Missing integration ID" title="Error" />}
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (!integration || (integration.scope === 'project' && assignmentsQuery.isPending)) return null

  return (
    <SynPage>
      <SynPageTitle segments={['Edit integration', 'Integrations']} />
      <SynPageHeader title="Edit integration" breadcrumbs={breadcrumbs} docLink={docLink} />
      <SynPageBody>
        <SynPanel
          isFullHeight
          isScrollable
          panelMainBodyProps={{ className: styles.panelBody }}
          footer={<EditFormFooter isSaving={isSaving} onCancel={() => detachPromise(navigate({ to: detailPath }))} />}
        >
          <Form
            id="edit-integration-form"
            className={styles.form}
            onSubmit={(e) => {
              e.preventDefault()
              detachPromise(handleSubmit(onSubmit)())
            }}
          >
            <EditIntegrationFormFields
              integration={integration}
              control={control}
              errors={errors}
              scope={scope}
              credentialId={credentialId}
              isTesting={isTesting}
              setValue={setValue}
              onTestConnection={handleTestConnection}
            />
          </Form>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
