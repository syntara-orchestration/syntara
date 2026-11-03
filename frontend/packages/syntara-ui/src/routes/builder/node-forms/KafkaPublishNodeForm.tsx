import { HelperText, HelperTextItem, Stack, StackItem } from '@patternfly/react-core'
import { use, useEffect, useMemo, type ReactNode } from 'react'

import { SynForm } from '../../../components/forms/SynForm'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { KafkaPublishConnectionFields } from './KafkaPublishConnectionFields'
import { kafkaPublishFormSchema, type KafkaPublishFormData } from './kafkaPublishFormSchema'
import { KafkaPublishMessageFields } from './KafkaPublishMessageFields'
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

function DeliveryGuidance() {
  return (
    <HelperText>
      <HelperTextItem>
        Kafka acknowledgment confirms broker receipt. Retries and reruns can publish another copy. Timeout or
        cancellation may leave delivery unconfirmed.
      </HelperTextItem>
    </HelperText>
  )
}

function KafkaPublishFields({ projectId }: Readonly<{ projectId?: string }>) {
  const readOnly = useIsVersionView()
  return (
    <Stack hasGutter>
      <StackItem>
        <KafkaPublishConnectionFields projectId={projectId} />
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
          hint={
            'JSON value or ${trigger.payload} (declare trigger inputs). Quote strings. null is JSON null, not a tombstone. Arrays are one record. Templates can appear inside JSON.'
          }
        />
      </StackItem>
      <StackItem>
        <KafkaPublishMessageFields />
      </StackItem>
      <StackItem>
        <DeliveryGuidance />
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
      credential_required: true,
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
          settingsContent={
            <Stack hasGutter>
              <StackItem>
                <NodeSettingsForm />
              </StackItem>
              <StackItem>
                <DeliveryGuidance />
              </StackItem>
            </Stack>
          }
        />
      </SynForm>
    </NodeFormContainer>
  )
}
