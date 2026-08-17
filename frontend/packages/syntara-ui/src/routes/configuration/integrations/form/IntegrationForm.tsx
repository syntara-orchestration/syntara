import { zodResolver } from '@hookform/resolvers/zod'
import {
  ActionList,
  ActionListGroup,
  ActionListItem,
  Button,
  Wizard,
  WizardFooterWrapper,
  WizardStep,
  useWizardContext,
} from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useCallback, useState } from 'react'
import { useForm, useWatch, type Resolver, type UseFormTrigger } from 'react-hook-form'

import { AppRoute } from '../../../../app/AppRoute'
import { breadcrumbsIntegrationConfigure } from '../../../../app/breadcrumbBuilders'
import { tanstackRouter } from '../../../../app/tanstackRouter'
import { integrationsClient } from '../../../../client'
import { NxPage, NxPageBody } from '../../../../components/layout/NxPage'
import { NxPageHeader } from '../../../../components/layout/NxPageHeader'
import { NxPanel } from '../../../../components/layout/NxPanel'
import { NxPageTitle } from '../../../../components/NxPageTitle'
import { useDirtyFormGuard } from '../../../../hooks/useDirtyFormGuard'
import { useFormMutationErrorHandler } from '../../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../../providers/alerts'
import { getErrorMessage } from '../../../../utils/apiErrors'
import { detachPromise } from '../../../../utils/detachPromise'
import { useDocLink } from '../../../../utils/docs/useDocLink'
import { CREDENTIAL_REQUIRED_TYPES } from '../integrationFilters'

import { CredentialStep } from './CredentialStep'
import { EnableModelsWrapper } from './EnableModelsStep'
import { EnableToolsWrapper } from './EnableToolsStep'
import { IntegrationDetailsStep } from './IntegrationDetailsStep'
import {
  integrationFormSchema,
  getStep1Fields,
  getDefaultConfiguration,
  type IntegrationFormData,
} from './integrationFormSchema'
import { useCreateIntegration } from './useCreateIntegration'
import styles from './WizardSteps.module.css'

type DiscoverResult = IntegrationsAPI.components['schemas']['DiscoverResult']
type InitialModelSelection = IntegrationsAPI.components['schemas']['InitialModelSelection']

function discoveredDescription(count: number, singular: string): string {
  if (count === 0) return 'Successfully connected. The integration is reachable.'
  const noun = count === 1 ? singular : `${singular}s`
  return `Successfully connected. Discovered ${String(count)} ${noun}.`
}

type WizardNavFooterProps = Readonly<{
  trigger: UseFormTrigger<IntegrationFormData>
  onSubmit: () => void
  credentialId: string | null | undefined
  integrationTypeValue: string
  scopeValue: string
  isCredentialRequired: boolean
  onDetailsStepValidated: () => void
}>

function WizardNavFooter({
  trigger,
  onSubmit,
  credentialId,
  integrationTypeValue,
  scopeValue,
  isCredentialRequired,
  onDetailsStepValidated,
}: WizardNavFooterProps) {
  const { goToNextStep, goToPrevStep, activeStep } = useWizardContext()
  const isFirst = activeStep.index === 1
  const isSecond = activeStep.id === 'credential'
  const isLast =
    activeStep.id === 'enable-tools' ||
    activeStep.id === 'enable-models' ||
    (integrationTypeValue !== IntegrationTypeEnum.MCP_SERVER &&
      integrationTypeValue !== IntegrationTypeEnum.LLM_PROVIDER &&
      activeStep.id === 'credential')

  const handleNext = useCallback(async () => {
    if (isFirst) {
      const fields = getStep1Fields(integrationTypeValue, scopeValue)
      const valid = await trigger(fields as (keyof IntegrationFormData)[])
      if (valid) {
        onDetailsStepValidated()
        await goToNextStep()
      }
      return
    }
    await goToNextStep()
  }, [trigger, isFirst, goToNextStep, integrationTypeValue, scopeValue, onDetailsStepValidated])

  const isNextDisabled = isSecond && isCredentialRequired && !credentialId
  const isSaveDisabled = isSecond && isCredentialRequired && !credentialId

  return (
    <WizardFooterWrapper>
      <ActionList>
        <ActionListGroup>
          {!isFirst && (
            <ActionListItem>
              <Button variant="secondary" onClick={goToPrevStep}>
                Back
              </Button>
            </ActionListItem>
          )}
          <ActionListItem>
            {isLast ? (
              <Button variant="primary" onClick={isSaveDisabled ? undefined : onSubmit} isAriaDisabled={isSaveDisabled}>
                Save
              </Button>
            ) : (
              <Button
                variant="primary"
                onClick={isNextDisabled ? undefined : () => detachPromise(handleNext())}
                isAriaDisabled={isNextDisabled}
              >
                Next
              </Button>
            )}
          </ActionListItem>
        </ActionListGroup>
        <ActionListGroup>
          <ActionListItem>
            <Button
              variant="link"
              onClick={() => {
                detachPromise(tanstackRouter.navigate({ to: AppRoute.Configuration.Integrations.Root }))
              }}
            >
              Cancel
            </Button>
          </ActionListItem>
        </ActionListGroup>
      </ActionList>
    </WizardFooterWrapper>
  )
}

function useDiscoverConnection(getValues: () => IntegrationFormData) {
  const [testResult, setTestResult] = useState<DiscoverResult | null>(null)
  const [selectedToolNames, setSelectedToolNames] = useState<Set<string>>(new Set())
  const [selectedModels, setSelectedModels] = useState<Map<string, InitialModelSelection>>(new Map())

  const { mutate: testConnection, isPending: isTesting } = integrationsClient.useMutation(
    'post',
    '/integrations/discover'
  )
  const { showAlert } = useAlerts()

  const resetTestState = useCallback(() => {
    setTestResult(null)
    setSelectedToolNames(new Set())
    setSelectedModels(new Map())
  }, [])

  const handleDiscoverSuccess = useCallback(
    (result: DiscoverResult, isLLMType: boolean) => {
      setTestResult(result)
      if (!result.success) {
        showAlert({
          title: 'Connection failed',
          description: result.error ?? 'Unable to connect to the integration.',
          variant: 'danger',
          autoDismiss: true,
        })
        return
      }

      if (isLLMType) {
        const discoveredModels = result.discovered_models ?? []
        const modelMap = new Map<string, InitialModelSelection>()
        for (const model of discoveredModels) {
          modelMap.set(model.id, {
            model_id: model.id,
            name: model.name,
            description: model.description ?? null,
            enabled: true,
            is_default: false,
          })
        }
        setSelectedModels(modelMap)
        showAlert({
          title: 'Connection tested',
          description: discoveredDescription(discoveredModels.length, 'model'),
          variant: 'success',
          autoDismiss: true,
        })
      } else {
        setSelectedToolNames(new Set(result.discovered_tools?.map((t) => t.name) ?? []))
        showAlert({
          title: 'Connection tested',
          description: discoveredDescription(result.discovered_tools?.length ?? 0, 'tool'),
          variant: 'success',
          autoDismiss: true,
        })
      }
    },
    [showAlert]
  )

  const handleTestConnection = useCallback(() => {
    const values = getValues()
    const credId = values.management_credential_id
    if (!credId && CREDENTIAL_REQUIRED_TYPES.has(values.integration_type)) return

    resetTestState()

    const isLLMType = values.integration_type === IntegrationTypeEnum.LLM_PROVIDER
    testConnection(
      {
        body: {
          integration_type: values.integration_type,
          configuration: values.configuration,
          credential_id: credId ?? undefined,
        },
      },
      {
        onSuccess: (result) => handleDiscoverSuccess(result, isLLMType),
        onError: (error: unknown) => {
          showAlert({
            title: 'Connection test failed',
            description: getErrorMessage(error),
            variant: 'danger',
            autoDismiss: true,
          })
        },
      }
    )
  }, [getValues, testConnection, showAlert, resetTestState, handleDiscoverSuccess])

  return {
    testResult,
    selectedToolNames,
    setSelectedToolNames,
    selectedModels,
    setSelectedModels,
    isTesting,
    resetTestState,
    handleTestConnection,
  }
}

export function IntegrationForm() {
  const docLink = useDocLink('configureIntegration')
  // zodResolver with discriminated unions produces a resolver type that react-hook-form
  // cannot reconcile — the TFieldValues generic diverges. This is a known @hookform/resolvers
  // limitation. The cast is safe because the schema defines the actual validation.
  const {
    control,
    handleSubmit,
    setError,
    trigger,
    setValue,
    getValues,
    formState: { isDirty },
    reset,
  } = useForm<IntegrationFormData>({
    resolver: zodResolver(integrationFormSchema, undefined, { mode: 'sync' }) as Resolver<IntegrationFormData>,
    defaultValues: {
      name: '',
      description: '',
      integration_type: IntegrationTypeEnum.MCP_SERVER,
      configuration: {
        integration_type: IntegrationTypeEnum.MCP_SERVER,
        base_url: '',
        allow_http: false,
        insecure_skip_tls_verify: false,
        ca_certificate: null,
      },
      management_credential_id: null,
      scope: 'global',
      project_ids: [],
    },
  })
  const handleError = useFormMutationErrorHandler<IntegrationFormData>(setError)

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => reset(),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this integration. Your changes will be lost if you leave.',
  })
  const createIntegration = useCreateIntegration({ handleError, onBeforeNavigate: dismiss })
  const credentialId = useWatch({ control, name: 'management_credential_id' })
  const integrationTypeValue = useWatch({ control, name: 'integration_type' })
  const scopeValue = useWatch({ control, name: 'scope' })

  const {
    testResult,
    selectedToolNames,
    setSelectedToolNames,
    selectedModels,
    setSelectedModels,
    isTesting,
    resetTestState,
    handleTestConnection,
  } = useDiscoverConnection(getValues)

  const [isDetailsStepValid, setIsDetailsStepValid] = useState(false)
  const { showAlert } = useAlerts()
  const isLLM = integrationTypeValue === IntegrationTypeEnum.LLM_PROVIDER
  const isCredentialRequired = CREDENTIAL_REQUIRED_TYPES.has(integrationTypeValue)

  const onTypeChange = useCallback(
    (newType: string) => {
      setValue('configuration', getDefaultConfiguration(newType), { shouldValidate: false })
      setValue('integration_type', newType as IntegrationFormData['integration_type'])
      setValue('management_credential_id', null)
      resetTestState()
      setIsDetailsStepValid(false)
    },
    [setValue, resetTestState]
  )

  const onSubmit = handleSubmit(
    (formData) => {
      if (formData.integration_type === IntegrationTypeEnum.LLM_PROVIDER) {
        const discoveredModels = Array.from(selectedModels.values())
        createIntegration(formData, undefined, discoveredModels)
      } else {
        const discoveredTools = testResult?.discovered_tools?.map((tool) => ({
          name: tool.name,
          description: tool.description,
          enabled: selectedToolNames.has(tool.name),
          parameters: tool.parameters as
            | { name: string; type?: string; description?: string; required?: boolean }[]
            | undefined,
        }))
        createIntegration(formData, discoveredTools)
      }
    },
    (errors) => {
      const messages: string[] = []
      if (errors.name) messages.push(errors.name.message ?? 'Name is invalid')
      if (errors.configuration && 'base_url' in errors.configuration && errors.configuration.base_url) {
        messages.push(errors.configuration.base_url.message ?? 'Base URL is invalid')
      }
      if (messages.length > 0) {
        showAlert({
          title: 'Unable to save integration',
          description: messages.join('. '),
          variant: 'danger',
          autoDismiss: true,
        })
      }
    }
  )

  return (
    <NxPage>
      <NxPageTitle segments={['Configure integration', 'Integrations']} />
      <NxPageHeader title="Configure integration" breadcrumbs={breadcrumbsIntegrationConfigure()} docLink={docLink} />
      <NxPageBody>
        <NxPanel isFullHeight panelMainBodyProps={{ className: styles.wizardPanel }}>
          <Wizard
            isVisitRequired
            footer={
              <WizardNavFooter
                trigger={trigger}
                onSubmit={() => detachPromise(onSubmit())}
                credentialId={credentialId}
                integrationTypeValue={integrationTypeValue}
                scopeValue={scopeValue}
                isCredentialRequired={isCredentialRequired}
                onDetailsStepValidated={() => setIsDetailsStepValid(true)}
              />
            }
          >
            <WizardStep name="Integration details" id="integration-details">
              <IntegrationDetailsStep control={control} setValue={setValue} onTypeChange={onTypeChange} />
            </WizardStep>

            <WizardStep name="Connection credential" id="credential" navItem={{ isDisabled: !isDetailsStepValid }}>
              <CredentialStep
                control={control}
                setValue={setValue}
                credentialId={credentialId}
                integrationTypeValue={integrationTypeValue}
                isTesting={isTesting}
                onTestConnection={handleTestConnection}
                onCredentialChange={resetTestState}
              />
            </WizardStep>

            <WizardStep
              name="Enable tools"
              id="enable-tools"
              isHidden={integrationTypeValue !== IntegrationTypeEnum.MCP_SERVER}
              isDisabled={isCredentialRequired && !credentialId}
            >
              <EnableToolsWrapper
                testResult={testResult}
                selectedNames={selectedToolNames}
                onSelectionChange={setSelectedToolNames}
                onTestConnection={handleTestConnection}
                isTestDisabled={(isCredentialRequired && !credentialId) || isTesting}
              />
            </WizardStep>

            <WizardStep
              name="Enable models"
              id="enable-models"
              isHidden={!isLLM}
              isDisabled={isCredentialRequired && !credentialId}
            >
              <EnableModelsWrapper
                testResult={testResult}
                selectedModels={selectedModels}
                onSelectionChange={setSelectedModels}
                onTestConnection={handleTestConnection}
                isTestDisabled={(isCredentialRequired && !credentialId) || isTesting}
              />
            </WizardStep>
          </Wizard>
        </NxPanel>
      </NxPageBody>
    </NxPage>
  )
}
