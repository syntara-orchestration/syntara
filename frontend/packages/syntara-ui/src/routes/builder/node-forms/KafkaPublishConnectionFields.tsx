import { Stack, StackItem } from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { useEffect } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { integrationsClient } from '../../../client'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynErrorState } from '../../../components/states/SynErrorState'
import { detachPromise } from '../../../utils/detachPromise'
import { useCredentialName } from '../../workflows/canvas/nodes/hooks/useCredentialName'
import { CredentialSelector } from '../components/CredentialSelector'
import { IntegrationSelector } from '../components/IntegrationSelector'
import { useIsVersionView } from '../VersionViewContext'

import { KafkaCredentialConnection } from './KafkaCredentialConnection'
import styles from './KafkaPublishConnectionFields.module.css'
import type { KafkaPublishFormData } from './kafkaPublishFormSchema'

export function KafkaPublishConnectionFields({ projectId }: Readonly<{ projectId?: string }>) {
  const {
    control,
    setValue,
    trigger,
    formState: { isSubmitted },
  } = useFormContext<KafkaPublishFormData>()
  const integrationId = useWatch({ control, name: 'integration_id' })
  const credentialId = useWatch({ control, name: 'credential_id' })
  const { name: credentialName, isPending: isCredentialPending } = useCredentialName(credentialId || undefined)
  const readOnly = useIsVersionView()
  const { data, isError, error, refetch } = integrationsClient.useQuery(
    'get',
    '/kafka_integrations/{integration_id}',
    {
      params: { path: { integration_id: integrationId } },
    },
    { enabled: !!integrationId }
  )
  const connectionReady = !!integrationId && !!data && !isError

  // Synchronize validation with the connection returned by the Integration API.
  useEffect(() => {
    setValue('connection_ready', connectionReady)
    if (isSubmitted) detachPromise(trigger(['integration_id', 'connection_ready', 'credential_id']))
  }, [connectionReady, integrationId, isSubmitted, setValue, trigger])

  return (
    <Stack className={styles.connectionFields}>
      <StackItem>
        <SynFormField<KafkaPublishFormData, 'integration_id'>
          name="integration_id"
          label="Integration"
          hideFormGroupLabel
        >
          {({ field }) => (
            <IntegrationSelector
              integrationType={IntegrationTypeEnum.KAFKA}
              label="Integration"
              isRequired
              fieldId="publish-integration"
              placeholder="Select a Kafka integration"
              projectId={projectId}
              value={field.value}
              isDisabled={readOnly}
              onChange={(value) => {
                if ((value ?? '') === field.value) return
                field.onChange(value ?? '')
                setValue('credential_id', '', { shouldDirty: true })
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
      {integrationId && (
        <StackItem>
          <SynFormField<KafkaPublishFormData, 'credential_id'>
            name="credential_id"
            label="Runtime credential"
            hideFormGroupLabel
            hideFooter
          >
            {({ field, fieldState }) => (
              <KafkaCredentialConnection
                key={integrationId}
                credentialName={credentialName}
                credentialLabel="Kafka credential"
                isPending={(!connectionReady && !isError) || isCredentialPending}
                isDisabled={readOnly || isError}
                isRequired
                isCompact
                errorMessage={fieldState.error?.message}
              >
                {(onSelected) => (
                  <CredentialSelector
                    label="Runtime credential"
                    hideLabel
                    fieldId="publish-credential"
                    placeholder="Select a credential"
                    projectId={projectId}
                    compatibleTypeNames={['Kafka']}
                    value={field.value || undefined}
                    onChange={(value) => {
                      field.onChange(value ?? '')
                      onSelected()
                    }}
                    errorMessage={fieldState.error?.message}
                    isRequired
                    isDisabled={readOnly || !connectionReady}
                  />
                )}
              </KafkaCredentialConnection>
            )}
          </SynFormField>
        </StackItem>
      )}
    </Stack>
  )
}
