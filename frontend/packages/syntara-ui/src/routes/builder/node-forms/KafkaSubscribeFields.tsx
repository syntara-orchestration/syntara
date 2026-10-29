import { Alert, Content, ContentVariants, Stack, StackItem } from '@patternfly/react-core'
import { useFormContext, useWatch } from 'react-hook-form'

import { FormLabelWithHelp } from '../../../components/FormLabelWithHelp'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { CredentialSelector } from '../components/CredentialSelector'
import { useIsVersionView } from '../VersionViewContext'

import { KafkaIntegrationField } from './KafkaIntegrationField'
import { kafkaSubscribeParameters } from './kafkaSubscribeMapping'
import { KafkaSubscribePreflight } from './KafkaSubscribePreflight'
import { PayloadValidationSection } from './PayloadValidationSection'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { DEFAULT_JSON_SCHEMA, EXAMPLE_JSON_SCHEMA, triggerFormSchema, type TriggerFormData } from './triggerFormSchema'

const KAFKA_CREDENTIAL_TYPES = ['Kafka']

export function KafkaSubscribeFields({
  workflowId,
  projectId,
}: Readonly<{ workflowId?: string | null; projectId?: string }>) {
  const isReadOnly = useIsVersionView()
  const { control, setValue } = useFormContext<TriggerFormData>()
  const values = useWatch({ control })
  const parsed = triggerFormSchema.safeParse(values)
  const parameters =
    parsed.success && values.integrationId && values.runtimeCredentialId && values.topic
      ? kafkaSubscribeParameters(parsed.data)
      : undefined
  const preflightKey = JSON.stringify([
    workflowId,
    projectId,
    values.integrationId,
    values.runtimeCredentialId,
    values.topic,
    values.inputSchema,
  ])

  return (
    <Stack hasGutter>
      <StackItem>
        <Alert variant="info" isInline title="Kafka Subscribe activation" component="h4">
          <Content component={ContentVariants.p}>
            Publishing activates this subscription. The runtime credential authenticates to Kafka. The platform supplies
            the workflow execution identity automatically.
          </Content>
        </Alert>
      </StackItem>
      <StackItem>
        <fieldset disabled={isReadOnly} className={nodeFormStyles.disabledFieldset}>
          <Stack hasGutter>
            <StackItem>
              <KafkaIntegrationField projectId={projectId} isDisabled={isReadOnly} />
            </StackItem>
            <StackItem>
              <SynFormField<TriggerFormData, 'runtimeCredentialId'>
                name="runtimeCredentialId"
                label=""
                hideFormGroupLabel
                hideFooter
              >
                {({ field, fieldState }) => (
                  <CredentialSelector
                    value={field.value}
                    onChange={(value) =>
                      setValue('runtimeCredentialId', value ?? '', { shouldDirty: true, shouldValidate: true })
                    }
                    projectId={projectId}
                    compatibleTypeNames={KAFKA_CREDENTIAL_TYPES}
                    label="Kafka runtime credential"
                    fieldId="kafka-runtime-credential"
                    isRequired
                    allowCreate={false}
                    isDisabled={isReadOnly || !values.integrationId}
                    errorMessage={fieldState.error?.message}
                    helpText="Used to authenticate this subscription to Kafka. Select a Kafka credential explicitly; the Integration management credential is not substituted. This does not select the workflow execution identity."
                  />
                )}
              </SynFormField>
            </StackItem>
            <StackItem>
              <SynTextField
                name="topic"
                label="Topic"
                fieldId="kafka-topic"
                isRequired
                isDisabled={isReadOnly}
                placeholder="orders.created"
                hint="One exact Kafka topic. Expressions, wildcards, and topic lists are not supported."
              />
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
        <Content component={ContentVariants.p}>
          Each subscription uses a platform-managed group. Partitions present at first activation start with new
          messages at the visible-end boundary saved when each partition initializes. Partitions added later start at
          their earliest retained message. Initialized partitions resume from valid committed offsets. Missing or
          invalid established checkpoints require recovery; they do not reset automatically. Auto-commit is off. Commit
          follows durable scheduling or resolution, without waiting for workflow completion.
        </Content>
      </StackItem>
      <StackItem>
        <KafkaSubscribePreflight
          key={preflightKey}
          workflowId={workflowId}
          projectId={projectId}
          parameters={parameters}
          isReadOnly={isReadOnly}
        />
      </StackItem>
    </Stack>
  )
}
