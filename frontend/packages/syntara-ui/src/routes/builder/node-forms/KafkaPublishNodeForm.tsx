import { Stack, StackItem } from '@patternfly/react-core'
import { use, useEffect, useMemo, type ReactNode } from 'react'

import { SynForm } from '../../../components/forms/SynForm'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { KafkaPublishConnectionFields } from './KafkaPublishConnectionFields'
import { KafkaPublishDeliveryAlert } from './KafkaPublishDeliveryAlert'
import { kafkaPublishFormSchema, type KafkaPublishFormData } from './kafkaPublishFormSchema'
import { KafkaPublishMessageFields } from './KafkaPublishMessageFields'
import { KafkaPublishPayloadField } from './KafkaPublishPayloadField'
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
  const readOnly = useIsVersionView()
  return (
    <Stack hasGutter>
      <StackItem>
        <KafkaPublishDeliveryAlert />
      </StackItem>
      <StackItem>
        <KafkaPublishConnectionFields projectId={projectId} />
      </StackItem>
      <StackItem>
        <SynTextField
          name="topic"
          label="Target topic"
          fieldId="publish-topic"
          isRequired
          isDisabled={readOnly}
          hint="Enter an existing Kafka topic name. Expressions are not supported."
        />
      </StackItem>
      <StackItem>
        <KafkaPublishPayloadField />
      </StackItem>
      <StackItem>
        <KafkaPublishMessageFields />
      </StackItem>
    </Stack>
  )
}

export function KafkaPublishNodeForm(props: Readonly<KafkaPublishNodeFormProps>) {
  const { onHeaderContentChange } = props
  const form = useSynForm<KafkaPublishFormData>({
    schema: kafkaPublishFormSchema,
    mode: 'onChange',
    defaultValues: {
      name: '',
      integration_id: '',
      credential_id: '',
      connection_ready: false,
      topic: '',
      payload: '{}',
      key: { encoding: 'null', value: '' },
      headers_mode: 'entries',
      headers: [],
      headers_template: '',
      settings: {},
      ...props.initialData,
    },
  })
  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, props.onSubmit, { allowIncomplete: true })
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
    <NodeFormContainer
      formId="kafka-publish-node-form"
      onSubmit={form.handleSubmit(props.onSubmit, () => props.onSubmit(form.getValues()))}
    >
      <SynForm form={form}>
        <NodeFormTabsLayout
          parametersContent={<KafkaPublishFields projectId={props.projectId} />}
          settingsContent={<NodeSettingsForm />}
        />
      </SynForm>
    </NodeFormContainer>
  )
}
