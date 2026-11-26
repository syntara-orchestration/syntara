import { Stack, StackItem, TextInput } from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { use } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { FormFieldError } from '../../../components/FormFieldError'
import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { SynFormField } from '../../../components/forms/SynFormField'
import { CredentialSelector } from '../components/CredentialSelector'
import { IntegrationSelector } from '../components/IntegrationSelector'
import { useIsVersionView } from '../VersionViewContext'

import { KafkaConsumerSettings } from './KafkaConsumerSettings'
import { KafkaCredentialConnection } from './KafkaCredentialConnection'
import { KafkaSubscribeBehaviorAlert } from './KafkaSubscribeBehaviorAlert'
import { KafkaSubscribeFilter } from './KafkaSubscribeFilter'
import { kafkaSubscribeParameters } from './kafkaSubscribeMapping'
import { KafkaSubscribePreflight } from './KafkaSubscribePreflight'
import { KafkaSubscribeResourceContext } from './kafkaSubscribeResourceContext'
import { PayloadValidationSection } from './PayloadValidationSection'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { DEFAULT_JSON_SCHEMA, EXAMPLE_JSON_SCHEMA, triggerFormSchema, type TriggerFormData } from './triggerFormSchema'
import { kafkaResourceErrors } from './useKafkaSubscribeResources'

const KAFKA_CREDENTIAL_TYPES = ['Kafka']

export function KafkaSubscribeFields({
  workflowId,
  projectId,
  triggerId,
}: Readonly<{ workflowId?: string | null; projectId?: string; triggerId?: string }>) {
  const isReadOnly = useIsVersionView()
  const resources = use(KafkaSubscribeResourceContext)
  const { control, setValue } = useFormContext<TriggerFormData>()
  const values = useWatch({ control })
  const parsed = triggerFormSchema.safeParse(values)
  const resourceErrors = resources ? kafkaResourceErrors(values, resources) : {}
  const resourcesLoading = Boolean(
    resources?.integrations.isPending || resources?.credentials.isLoading || resources?.types.isPending
  )
  const ready =
    parsed.success &&
    values.integrationId &&
    values.runtimeCredentialId &&
    values.topic &&
    !Object.keys(resourceErrors).length
  const parameters = ready ? kafkaSubscribeParameters(parsed.data) : undefined
  const preflightKey = JSON.stringify([
    workflowId,
    projectId,
    values.integrationId,
    values.runtimeCredentialId,
    values.topic,
    values.inputSchema,
    values.filterExpression,
    values.kafkaStart,
    values.kafkaGroupId,
    resourceErrors,
  ])

  return (
    <Stack hasGutter>
      <StackItem>
        <KafkaSubscribeBehaviorAlert />
      </StackItem>
      <StackItem>
        <fieldset disabled={isReadOnly} className={nodeFormStyles.disabledFieldset}>
          <Stack hasGutter>
            <StackItem>
              <SynFormField<TriggerFormData, 'integrationId'>
                name="integrationId"
                label="Integration"
                hideFormGroupLabel
                hideFooter
              >
                {({ field }) => (
                  <IntegrationSelector
                    integrationType={IntegrationTypeEnum.KAFKA}
                    label="Integration"
                    isRequired
                    fieldId="subscribe-integration"
                    placeholder="Select a Kafka integration"
                    projectId={projectId}
                    value={field.value || undefined}
                    isDisabled={isReadOnly}
                    onChange={(value) => {
                      const next = value ?? ''
                      if (next === (field.value ?? '')) return
                      setValue('integrationId', next, { shouldDirty: true, shouldValidate: true })
                      setValue('runtimeCredentialId', '', { shouldDirty: true, shouldValidate: true })
                      setValue('kafkaGroupId', null, { shouldDirty: true, shouldValidate: true })
                    }}
                  />
                )}
              </SynFormField>
              <FormFieldError
                id="subscribe-integration-error"
                message={resources?.integrations.isPending ? undefined : resourceErrors.integrationId}
              />
            </StackItem>
            {values.integrationId && (
              <StackItem>
                <SynFormField<TriggerFormData, 'runtimeCredentialId'>
                  name="runtimeCredentialId"
                  label="Runtime credential"
                  hideFormGroupLabel
                  hideFooter
                >
                  {({ field, fieldState }) => (
                    <KafkaCredentialConnection
                      key={values.integrationId}
                      credentialName={resources?.credentials.credentials.find((item) => item.id === field.value)?.name}
                      credentialLabel="Kafka credential"
                      isPending={resourcesLoading}
                      errorMessage={resourceErrors.runtimeCredentialId ?? fieldState.error?.message}
                      isDisabled={isReadOnly}
                      isRequired
                      isCompact
                    >
                      {(onSelected) => (
                        <CredentialSelector
                          value={field.value}
                          onChange={(value) => {
                            setValue('runtimeCredentialId', value ?? '', { shouldDirty: true, shouldValidate: true })
                            onSelected()
                          }}
                          projectId={projectId}
                          compatibleTypeNames={KAFKA_CREDENTIAL_TYPES}
                          label="Runtime credential"
                          hideLabel
                          fieldId="subscribe-credential"
                          placeholder="Select a credential"
                          isRequired
                          isDisabled={isReadOnly || !values.integrationId || resourcesLoading}
                          errorMessage={
                            resourcesLoading
                              ? undefined
                              : (resourceErrors.runtimeCredentialId ?? fieldState.error?.message)
                          }
                        />
                      )}
                    </KafkaCredentialConnection>
                  )}
                </SynFormField>
              </StackItem>
            )}
            <StackItem>
              <SynFormField<TriggerFormData, 'topic'>
                name="topic"
                label="Topic"
                fieldId="kafka-topic"
                isRequired
                hint="One exact Kafka topic. Expressions, wildcards, and topic lists are not supported."
              >
                {({ field, fieldState, describedBy }) => (
                  <TextInput
                    id="kafka-topic"
                    name={field.name}
                    ref={field.ref}
                    value={field.value ?? ''}
                    onBlur={field.onBlur}
                    isRequired
                    isDisabled={isReadOnly}
                    placeholder="orders.created"
                    validated={fieldState.error ? 'error' : 'default'}
                    aria-describedby={describedBy}
                    onChange={(_event, value) => {
                      if (value !== field.value)
                        setValue('kafkaGroupId', null, { shouldDirty: true, shouldValidate: true })
                      field.onChange(value)
                    }}
                  />
                )}
              </SynFormField>
            </StackItem>
            <StackItem>
              <PayloadValidationSection
                label={
                  <FormLabelWithHelp
                    label="Payload schema"
                    helpText="Optional JSON Schema for the event payload. Leave empty to omit payload validation."
                  />
                }
                defaultCode={DEFAULT_JSON_SCHEMA}
                exampleCode={EXAMPLE_JSON_SCHEMA}
                modalTitle="Edit payload schema"
                ariaLabel="Payload schema editor"
                downloadFilename="payload-schema.json"
                helperText="Optional JSON Schema for the Kafka message payload."
              />
            </StackItem>
          </Stack>
        </fieldset>
      </StackItem>
      <StackItem>
        <KafkaSubscribeFilter isReadOnly={isReadOnly} />
      </StackItem>
      <StackItem>
        <KafkaConsumerSettings workflowId={workflowId} triggerId={triggerId} isReadOnly={isReadOnly} />
      </StackItem>
      <StackItem>
        <KafkaSubscribePreflight
          key={preflightKey}
          workflowId={workflowId}
          projectId={projectId}
          parameters={parameters}
          isLoading={resourcesLoading}
          isReadOnly={isReadOnly}
        />
      </StackItem>
    </Stack>
  )
}
