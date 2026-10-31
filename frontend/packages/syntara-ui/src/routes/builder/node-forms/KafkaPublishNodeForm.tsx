import { Stack, StackItem } from '@patternfly/react-core'
import { IntegrationTypeEnum } from '@syntara/contracts'
import { use, useEffect, useMemo, type ReactNode } from 'react'
import { useFormContext } from 'react-hook-form'

import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { CredentialSelector } from '../components/CredentialSelector'
import { IntegrationSelector } from '../components/IntegrationSelector'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { kafkaPublishFormSchema, type KafkaPublishFormData } from './kafkaPublishFormSchema'
import { ActivityNameField } from './shared/ActivityNameField'
import { NodeFormContainer } from './shared/NodeFormContainer'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'

type KafkaPublishNodeFormProps = {
  onSubmit: (data: KafkaPublishFormData) => void
  initialData?: Partial<KafkaPublishFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
}

function KafkaPublishFields({ projectId }: Readonly<{ projectId?: string }>) {
  const { setValue } = useFormContext<KafkaPublishFormData>()
  const readOnly = useIsVersionView()
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
              }}
            />
          )}
        </SynFormField>
      </StackItem>
      <StackItem>
        <SynFormField<KafkaPublishFormData, 'credential_id'>
          name="credential_id"
          label="Runtime credential"
          hideFormGroupLabel
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
              isDisabled={readOnly}
            />
          )}
        </SynFormField>
      </StackItem>
      <StackItem>
        <SynTextField
          name="topic"
          label="Topic"
          fieldId="publish-topic"
          isRequired
          isDisabled={readOnly}
          hint="An existing topic. The destination is fixed for this workflow version."
        />
      </StackItem>
      <StackItem>
        <SynTextAreaField
          name="payload"
          label="JSON payload"
          fieldId="publish-payload"
          rows={6}
          isRequired
          isDisabled={readOnly}
          hint={'Any JSON value, including null. Use ${trigger.payload} to preserve a value from workflow data.'}
        />
      </StackItem>
      <StackItem>
        <SynTextAreaField
          name="key"
          label="Message key"
          fieldId="publish-key"
          rows={3}
          isDisabled={readOnly}
          hint={'Optional. For example: {"encoding":"utf-8","value":"order-123"}. Use base64 for binary bytes.'}
        />
      </StackItem>
      <StackItem>
        <SynTextAreaField
          name="headers"
          label="Message headers"
          fieldId="publish-headers"
          rows={5}
          isDisabled={readOnly}
          hint={
            'An ordered JSON list. For example: [{"name":"correlation-id","value":{"encoding":"utf-8","value":"request-123"}}]. Duplicate names and null values are supported.'
          }
        />
      </StackItem>
    </Stack>
  )
}

export function KafkaPublishNodeForm(props: Readonly<KafkaPublishNodeFormProps>) {
  const { onHeaderContentChange } = props
  const form = useSynForm({
    schema: kafkaPublishFormSchema,
    mode: 'onChange',
    defaultValues: {
      name: '',
      integration_id: '',
      credential_id: '',
      topic: '',
      payload: '{}',
      key: '',
      headers: '[]',
      settings: {},
      ...props.initialData,
    },
  })
  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, props.onSubmit)
  const header = useMemo(
    () => (
      <ActivityNameField<KafkaPublishFormData>
        fieldId="publish-name"
        control={form.control}
        placeholder="Publish to Kafka"
        ariaLabel="Name"
      />
    ),
    [form.control]
  )
  useEffect(() => {
    onHeaderContentChange?.(header)
    return () => onHeaderContentChange?.(null)
  }, [header, onHeaderContentChange])
  return (
    <NodeFormContainer formId="kafka-publish-node-form" onSubmit={form.handleSubmit(props.onSubmit)}>
      <SynForm form={form}>
        <NodeFormTabsLayout
          parametersContent={<KafkaPublishFields projectId={props.projectId} />}
          settingsContent={<NodeSettingsForm />}
        />
      </SynForm>
    </NodeFormContainer>
  )
}
