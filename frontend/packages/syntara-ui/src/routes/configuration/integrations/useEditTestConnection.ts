import { IntegrationTypeEnum } from '@syntara/contracts'
import { useCallback } from 'react'

import { integrationsClient } from '../../../client'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'

import type { DiscoverResult, EditIntegrationFormValues, IntegrationRead } from './editIntegrationFormSchema'
import { buildConfiguration } from './editIntegrationFormSchema'
import { isIntegrationCredentialRequired } from './integrationFilters'
import { isLLMProvider, getProviderHint } from './integrationUtils'

export function useEditTestConnection(
  integration: IntegrationRead | undefined,
  getValues: () => EditIntegrationFormValues
) {
  const { showAlert } = useAlerts()
  const { mutate: testConnection, isPending: isTesting } = integrationsClient.useMutation(
    'post',
    '/integrations/discover'
  )

  const handleTestConnection = useCallback(() => {
    const values = getValues()
    const credId = values.management_credential_id
    if (
      !integration ||
      (!credId && isIntegrationCredentialRequired(integration.integration_type, values.security_protocol))
    )
      return

    const integrationType = integration.integration_type ?? IntegrationTypeEnum.MCP_SERVER
    const isLLMType = integrationType === IntegrationTypeEnum.LLM_PROVIDER

    testConnection(
      {
        body: {
          integration_type: integrationType,
          configuration: buildConfiguration(
            integrationType,
            values,
            isLLMProvider(integration) ? getProviderHint(integration) : undefined
          ),
          credential_id: credId ?? undefined,
        },
      },
      {
        onSuccess: (result: DiscoverResult) => {
          if (result.success) {
            const resourceCount = isLLMType
              ? (result.discovered_models?.length ?? 0)
              : (result.discovered_tools?.length ?? 0)
            const singular = isLLMType ? 'model' : 'tool'
            const resourceLabel = resourceCount === 1 ? singular : `${singular}s`
            showAlert({
              title: 'Connection tested',
              description:
                resourceCount > 0
                  ? `Successfully connected. Discovered ${String(resourceCount)} ${resourceLabel}.`
                  : 'Successfully connected. The integration is reachable.',
              variant: 'success',
              autoDismiss: true,
            })
          } else {
            showAlert({
              title: 'Connection failed',
              description: result.error ?? 'Unable to connect to the integration.',
              variant: 'danger',
              autoDismiss: true,
            })
          }
        },
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
  }, [getValues, testConnection, showAlert, integration])

  return { handleTestConnection, isTesting }
}
