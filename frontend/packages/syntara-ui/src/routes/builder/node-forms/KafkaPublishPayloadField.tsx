import { useRef } from 'react'
import { useWatch } from 'react-hook-form'

import { SynFormField } from '../../../components/forms/SynFormField'
import { ExpandableCodeEditor, type ExpandableCodeEditorHandle } from '../components/ExpandableCodeEditor'
import { useIsVersionView } from '../VersionViewContext'

import { isKafkaPublishPayloadTemplate, type KafkaPublishFormData } from './kafkaPublishFormSchema'
import { nodeHelp } from './shared/nodeFieldHelp'

const JSON_PAYLOAD_HINT =
  'Enter a valid JSON value (quote strings) or use a trigger input such as ${trigger.payload}. Declare referenced inputs in the trigger first. A JSON null is sent as JSON null, not as a Kafka tombstone.'

export function KafkaPublishPayloadField() {
  const readOnly = useIsVersionView()
  const cloudeventsMode = useWatch<KafkaPublishFormData, 'cloudevents_mode'>({ name: 'cloudevents_mode' })
  const label = cloudeventsMode ? 'Event data (JSON)' : 'JSON payload'
  const editorRef = useRef<ExpandableCodeEditorHandle | null>(null)

  return (
    <SynFormField<KafkaPublishFormData, 'payload'>
      name="payload"
      label={label}
      labelHelp={cloudeventsMode ? nodeHelp.kafkaPublishEventData : nodeHelp.kafkaPublishPayload}
      fieldId="publish-payload"
      isRequired
      hint={
        cloudeventsMode
          ? `Enter event data only; CloudEvents metadata is configured separately. ${JSON_PAYLOAD_HINT}`
          : JSON_PAYLOAD_HINT
      }
    >
      {({ field, fieldState, describedBy }) => (
        <div
          role="group"
          aria-label={label}
          aria-describedby={describedBy}
          className={fieldState.invalid ? 'pf-v6-c-form-control pf-m-error' : undefined}
        >
          <ExpandableCodeEditor
            ref={(handle) => {
              editorRef.current = handle
              field.ref(handle)
            }}
            code={field.value ?? ''}
            onCodeChange={field.onChange}
            onBlur={field.onBlur}
            onDropText={readOnly ? undefined : (text) => editorRef.current?.insertAtCursor(text)}
            language={isKafkaPublishPayloadTemplate(field.value ?? '') ? 'plaintext' : 'json'}
            height="200px"
            modalTitle={cloudeventsMode ? 'Edit event data (JSON)' : 'Edit JSON payload'}
            ariaLabel={label}
            isRequired
            isReadOnly={readOnly}
          />
        </div>
      )}
    </SynFormField>
  )
}
