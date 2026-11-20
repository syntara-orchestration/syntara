import {
  ActionGroup,
  Button,
  Content,
  ContentVariants,
  DescriptionList,
  Divider,
  Form,
  FormGroup,
  Title,
} from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, type ReactElement } from 'react'
import { useWatch, type UseFormSetValue } from 'react-hook-form'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsIntegrationEdit } from '../../../app/breadcrumbBuilders'
import { integrationsClient } from '../../../client'
import { SynDetail } from '../../../components/details/SynDetail'
import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { useDirtyFormGuard } from '../../../hooks/useDirtyFormGuard'
import { useSynForm } from '../../../hooks/useSynForm'
import { useAlerts } from '../../../providers/alerts/AlertContext'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { CredentialSelector } from '../../builder/components/CredentialSelector'

import styles from './EditIntegrationForm.module.css'
import type { EditIntegrationFormValues, IntegrationRead } from './editIntegrationFormSchema'
import { buildConfiguration, buildEditSchema, editIntegrationSchema } from './editIntegrationFormSchema'
import { EditSecurityFields } from './EditSecurityFields'
import { ExecutionPlaneScopeField } from './form/ExecutionPlaneScopeField'
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
  [IntegrationTypeEnum.OPENSHIFT]:
    'Use a service account token to authenticate to the cluster API. Credentials are stored encrypted in the platform credential store.',
}

type CredentialSectionCopy = {
  title: string
  description: string
  fieldLabel: string
  labelHelp: ReactElement
}

function getCredentialSectionCopy(integrationType: string): CredentialSectionCopy {
  if (integrationType === IntegrationTypeEnum.OPENSHIFT) {
    return {
      title: 'Authentication',
      description: CREDENTIAL_DESCRIPTION[IntegrationTypeEnum.OPENSHIFT],
      fieldLabel: 'Service account token',
      labelHelp: integrationHelp.serviceAccountToken,
    }
  }
  return {
    title: 'Connection credential',
    description: CREDENTIAL_DESCRIPTION[integrationType] ?? CREDENTIAL_DESCRIPTION[IntegrationTypeEnum.MCP_SERVER],
    fieldLabel: 'Health check credential',
    labelHelp: integrationHelp.healthCheckCredential,
  }
}

type EditDetailsFieldCopy = {
  nameLabel: string
  nameLabelHelp: ReactElement
  baseUrlLabel: string
  baseUrlLabelHelp: ReactElement
}

function getEditDetailsFieldCopy(integrationType: string, isLLM: boolean): EditDetailsFieldCopy {
  if (integrationType === IntegrationTypeEnum.OPENSHIFT) {
    return {
      nameLabel: 'Connection name',
      nameLabelHelp: integrationHelp.executionPlaneConnectionName,
      baseUrlLabel: 'API endpoint',
      baseUrlLabelHelp: integrationHelp.executionPlaneApiEndpoint,
    }
  }
  if (isLLM) {
    return {
      nameLabel: 'Name',
      nameLabelHelp: integrationHelp.name,
      baseUrlLabel: 'API URL',
      baseUrlLabelHelp: integrationHelp.apiUrl,
    }
  }
  if (integrationType === IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM) {
    return {
      nameLabel: 'Server name / ID',
      nameLabelHelp: integrationHelp.serverName,
      baseUrlLabel: 'API URL',
      baseUrlLabelHelp: integrationHelp.aapUrl,
    }
  }
  return {
    nameLabel: 'Server name / ID',
    nameLabelHelp: integrationHelp.serverName,
    baseUrlLabel: 'API URL',
    baseUrlLabelHelp: integrationHelp.apiUrl,
  }
}

type FormFieldsProps = Readonly<{
  integration: IntegrationRead
  scope: string
  credentialId: string | null | undefined
  isTesting: boolean
  setValue: UseFormSetValue<EditIntegrationFormValues>
  onTestConnection: () => void
}>

function EditIntegrationFormFields({
  integration,
  scope,
  credentialId,
  isTesting,
  setValue,
  onTestConnection,
}: FormFieldsProps) {
  const integrationType = integration.integration_type ?? IntegrationTypeEnum.MCP_SERVER
  const isCredentialRequired = CREDENTIAL_REQUIRED_TYPES.has(integrationType)
  const isTestDisabled = (isCredentialRequired && !credentialId) || isTesting
  const isOpenShift = integrationType === IntegrationTypeEnum.OPENSHIFT
  const isLLM = isLLMProvider(integration)
  const hideBaseUrl = isLLM && PROVIDERS_HIDING_BASE_URL.has(getProviderHint(integration))
  const credentialCopy = getCredentialSectionCopy(integrationType)
  const { nameLabel, nameLabelHelp, baseUrlLabel, baseUrlLabelHelp } = getEditDetailsFieldCopy(integrationType, isLLM)

  return (
    <>
      <Title headingLevel="h2" size="lg">
        Integration details
      </Title>

      <DescriptionList isCompact isHorizontal>
        <SynDetail label="Integration type">{INTEGRATION_TYPE_LABELS[integrationType] ?? integrationType}</SynDetail>
        {isOpenShift && <SynDetail label="Infrastructure type">OpenShift</SynDetail>}
        {isLLM && (
          <SynDetail label="Provider type">
            {PROVIDER_HINT_LABELS[getProviderHint(integration)] ?? getProviderHint(integration)}
          </SynDetail>
        )}
      </DescriptionList>

      <SynTextField<EditIntegrationFormValues, 'name'>
        name="name"
        label={nameLabel}
        fieldId="edit-name"
        isRequired
        labelHelp={nameLabelHelp}
      />

      {!isOpenShift && (
        <SynTextAreaField<EditIntegrationFormValues, 'description'>
          name="description"
          label="Description"
          fieldId="edit-description"
          resizeOrientation="vertical"
        />
      )}

      {!hideBaseUrl && (
        <SynTextField<EditIntegrationFormValues, 'base_url'>
          name="base_url"
          label={baseUrlLabel}
          fieldId="edit-base-url"
          isRequired={!isLLM}
          labelHelp={baseUrlLabelHelp}
        />
      )}

      <EditSecurityFields />

      {isOpenShift ? (
        <ExecutionPlaneScopeField fieldId="edit-integration-scope" />
      ) : (
        <ScopeFields<EditIntegrationFormValues>
          scope={scope}
          scopeName="scope"
          projectIdsName="project_ids"
          idPrefix="edit-integration"
          onScopeChange={(newScope) => {
            if (newScope === 'global') setValue('project_ids', [])
          }}
        />
      )}

      <Divider />

      <div>
        <Title headingLevel="h2" size="lg" className={styles.credentialHeading}>
          {credentialCopy.title}
        </Title>
        <Content component={ContentVariants.p} className={styles.credentialDescription}>
          {credentialCopy.description}
        </Content>
      </div>

      <SynFormField<EditIntegrationFormValues, 'management_credential_id'>
        name="management_credential_id"
        label={credentialCopy.fieldLabel}
        fieldId="edit-credential-select"
        isRequired={isCredentialRequired}
        labelHelp={credentialCopy.labelHelp}
        hideFormGroupLabel
        hideFooter
      >
        {({ field }) => (
          <CredentialSelector
            value={field.value ?? undefined}
            onChange={(id) => setValue('management_credential_id', id ?? null)}
            compatibleTypeNames={CREDENTIAL_TYPES_BY_INTEGRATION[integrationType]}
            label={credentialCopy.fieldLabel}
            fieldId="edit-credential-select"
            isRequired={isCredentialRequired}
            allowCreate
            placeholder={isOpenShift ? 'Select or create a credential' : 'Select a credential'}
            labelHelp={credentialCopy.labelHelp}
          />
        )}
      </SynFormField>

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
  const isOpenShiftIntegration = integration?.integration_type === IntegrationTypeEnum.OPENSHIFT
  // OpenShift is always global in the UI/submit path, even if a bad record has scope: project.
  const isProjectScoped = !isOpenShiftIntegration && integration?.scope === 'project'

  const assignmentsQuery = integrationsClient.useQuery(
    'get',
    '/integrations/{integration_id}/projects',
    { params: { path: { integration_id: integrationId ?? '' } } },
    { enabled: isProjectScoped }
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
    initialProjectIdsRef.current = isProjectScoped ? initialProjectIds : []
  }, [isProjectScoped, initialProjectIds])

  const formValues = useMemo<EditIntegrationFormValues | undefined>(() => {
    if (!integration) return undefined
    const config = integration.configuration
    const isOpenShift = integration.integration_type === IntegrationTypeEnum.OPENSHIFT
    // OpenShift always requires HTTPS + TLS verification — coerce like scope:global.
    const scope = isOpenShift ? 'global' : ((integration.scope as 'global' | 'project') ?? 'global')
    const projectIds = isProjectScoped ? initialProjectIds : []
    const allowHttp = 'allow_http' in config ? Boolean(config.allow_http) : false
    const skipTls = 'insecure_skip_tls_verify' in config ? Boolean(config.insecure_skip_tls_verify) : false
    return {
      name: integration.name ?? '',
      description: integration.description ?? '',
      integration_type: integration.integration_type ?? IntegrationTypeEnum.MCP_SERVER,
      base_url: 'base_url' in config ? String(config.base_url ?? '') : '',
      allow_http: isOpenShift ? false : allowHttp,
      insecure_skip_tls_verify: isOpenShift ? false : skipTls,
      ca_certificate: 'ca_certificate' in config ? (config.ca_certificate ?? null) : null,
      scope,
      project_ids: projectIds,
      management_credential_id: integration.management_credential_id ?? null,
    }
  }, [integration, isProjectScoped, initialProjectIds])

  const form = useSynForm({
    schema,
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
  const {
    control,
    handleSubmit,
    handleError,
    setValue,
    getValues,
    reset,
    formState: { isDirty },
  } = form

  const scope = useWatch({ control, name: 'scope' })
  const credentialId = useWatch({ control, name: 'management_credential_id' })

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => reset(),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this integration. Your changes will be lost if you leave.',
  })

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
            {queryState ?? <SynErrorState message="Missing integration ID" title="Error" />}
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (!integration || (isProjectScoped && assignmentsQuery.isPending)) return null

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
            <SynForm form={form}>
              <EditIntegrationFormFields
                integration={integration}
                scope={scope}
                credentialId={credentialId}
                isTesting={isTesting}
                setValue={setValue}
                onTestConnection={handleTestConnection}
              />
            </SynForm>
          </Form>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
