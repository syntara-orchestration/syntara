import { Stack, StackItem } from '@patternfly/react-core'
import { use, useEffect, useMemo, type ReactNode } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { SynForm } from '../../../components/forms/SynForm'
import { SynSwitchField } from '../../../components/forms/SynSwitchField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useSynForm } from '../../../hooks/useSynForm'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { DroppableField } from '../panels/fields/DroppableField'
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
  const { getValues, setValue } = useFormContext<KafkaPublishFormData>()
  const readOnly = useIsVersionView()
  const cloudeventsMode = useWatch<KafkaPublishFormData, 'cloudevents_mode'>({ name: 'cloudevents_mode' })
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
          placeholder="orders"
          fieldId="publish-topic"
          isRequired
          isDisabled={readOnly}
          hint="Enter an existing Kafka topic name. Expressions are not supported."
        />
      </StackItem>
      <StackItem>
        <SynSwitchField
          name="cloudevents_mode"
          label="Publish as CloudEvent"
          fieldId="publish-cloudevents-mode"
          isDisabled={readOnly}
          hint={
            cloudeventsMode
              ? 'Set the event type and source. ce_specversion, ce_id, and ce_time are generated automatically.'
              : undefined
          }
        />
      </StackItem>
      {cloudeventsMode && (
        <>
          <StackItem>
            <DroppableField
              isDisabled={readOnly}
              onDropText={(text) =>
                setValue('ce_type', (getValues('ce_type') ?? '') + text, { shouldDirty: true, shouldValidate: true })
              }
            >
              <SynTextField
                name="ce_type"
                label="Event type (ce_type)"
                placeholder="com.example.event.created"
                fieldId="publish-ce-type"
                isRequired
                isDisabled={readOnly}
                hint="Enter a value or drag an expression from the Input panel"
              />
            </DroppableField>
          </StackItem>
          <StackItem>
            <DroppableField
              isDisabled={readOnly}
              onDropText={(text) =>
                setValue('ce_source', (getValues('ce_source') ?? '') + text, {
                  shouldDirty: true,
                  shouldValidate: true,
                })
              }
            >
              <SynTextField
                name="ce_source"
                label="Event source (ce_source)"
                placeholder="/orders/service"
                fieldId="publish-ce-source"
                isRequired
                isDisabled={readOnly}
                hint="Enter a value or drag an expression from the Input panel"
              />
            </DroppableField>
          </StackItem>
        </>
      )}
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
      cloudevents_mode: false,
      ce_type: '',
      ce_source: '',
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
