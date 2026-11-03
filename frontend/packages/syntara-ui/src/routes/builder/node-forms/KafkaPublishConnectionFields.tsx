import { Stack, StackItem } from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useEffect } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { integrationsClient } from '../../../client'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { detachPromise } from '../../../utils/detachPromise'
import { CredentialSelector } from '../components/CredentialSelector'
import { IntegrationSelector } from '../components/IntegrationSelector'
import { useIsVersionView } from '../VersionViewContext'

import type { KafkaPublishFormData } from './kafkaPublishFormSchema'

export function KafkaPublishConnectionFields({ projectId }: Readonly<{ projectId?: string }>) {
  const {
    control,
    setValue,
    trigger,
    formState: { isSubmitted },
  } = useFormContext<KafkaPublishFormData>()
  const integrationId = useWatch({ control, name: 'integration_id' })
  const readOnly = useIsVersionView()
  const { data, isError, error, refetch } = integrationsClient.useQuery(
    'get',
    '/kafka_integrations/{integration_id}',
    {
      params: { path: { integration_id: integrationId } },
    },
    { enabled: !!integrationId }
  )
  const credentialRequired = (data?.configuration.security_protocol ?? 'SASL_SSL') === 'SASL_SSL'
  const connectionReady = !!data && !isError

  // Synchronize validation with the connection returned by the Integration API.
  useEffect(() => {
    setValue('credential_required', credentialRequired)
    setValue('connection_ready', connectionReady)
    if (isSubmitted) detachPromise(trigger(['integration_id', 'credential_id']))
  }, [credentialRequired, connectionReady, integrationId, isSubmitted, setValue, trigger])

  return (
    <Stack hasGutter>
      <StackItem>
        <SynFormField<KafkaPublishFormData, 'integration_id'>
          name="integration_id"
          label="Kafka integration"
          hideFormGroupLabel
        >
          {({ field }) => (
            <IntegrationSelector
              integrationType={IntegrationTypeEnum.KAFKA}
              label="Kafka integration"
              fieldId="publish-integration"
              placeholder="Select a Kafka integration"
              projectId={projectId}
              value={field.value}
              isDisabled={readOnly}
              onChange={(value) => {
                field.onChange(value ?? '')
                setValue('credential_id', '', { shouldDirty: true })
                setValue('credential_required', true)
                setValue('connection_ready', false)
              }}
            />
          )}
        </SynFormField>
      </StackItem>
      {isError && (
        <StackItem>
          <SynErrorState
            title="Unable to load Kafka connection settings"
            message={error}
            onRetry={() => detachPromise(refetch())}
          />
        </StackItem>
      )}
      <StackItem>
        <SynFormField<KafkaPublishFormData, 'credential_id'>
          name="credential_id"
          label="Runtime credential"
          hideFormGroupLabel
          hideFooter
        >
          {({ field, fieldState }) => (
            <CredentialSelector
              label="Runtime credential"
              fieldId="publish-credential"
              projectId={projectId}
              compatibleTypeNames={['Kafka']}
              value={field.value || undefined}
              onChange={(value) => field.onChange(value ?? '')}
              errorMessage={fieldState.error?.message}
              isRequired={credentialRequired}
              isDisabled={readOnly || !connectionReady}
              helpText={
                credentialRequired
                  ? 'SASL_SSL requires a runtime Kafka credential. The integration’s management credential is never used for publishing.'
                  : 'SSL and opted-in PLAINTEXT connections allow omission. Any selected credential must be a Kafka credential. The integration’s management credential is never used for publishing.'
              }
            />
          )}
        </SynFormField>
      </StackItem>
    </Stack>
  )
}
