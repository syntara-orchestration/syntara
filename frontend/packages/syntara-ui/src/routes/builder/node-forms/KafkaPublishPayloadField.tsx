import { useRef } from 'react'

import { SynFormField } from '../../../components/forms/SynFormField'
import { ExpandableCodeEditor, type ExpandableCodeEditorHandle } from '../components/ExpandableCodeEditor'
import { useIsVersionView } from '../VersionViewContext'

import { isKafkaPublishPayloadTemplate, type KafkaPublishFormData } from './kafkaPublishFormSchema'
import { nodeHelp } from './shared/nodeFieldHelp'

export function KafkaPublishPayloadField() {
  const readOnly = useIsVersionView()
  const editorRef = useRef<ExpandableCodeEditorHandle | null>(null)

  return (
    <SynFormField<KafkaPublishFormData, 'payload'>
      name="payload"
      label="JSON payload"
      labelHelp={nodeHelp.kafkaPublishPayload}
      fieldId="publish-payload"
      isRequired
      hint="Enter a valid JSON value (quote strings) or use a trigger input such as ${trigger.payload}. Declare referenced inputs in the trigger first. A JSON null is sent as JSON null, not as a Kafka tombstone."
    >
      {({ field, fieldState, describedBy }) => (
        <div
          role="group"
          aria-label="JSON payload"
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
            modalTitle="Edit JSON payload"
            ariaLabel="JSON payload"
            isRequired
            isReadOnly={readOnly}
          />
        </div>
      )}
    </SynFormField>
  )
}
