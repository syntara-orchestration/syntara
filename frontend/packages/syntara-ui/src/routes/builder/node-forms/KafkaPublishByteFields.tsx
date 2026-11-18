import { Stack, StackItem, TextArea } from '@patternfly/react-core'
import type { DragEvent } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { isDragData, DRAG_TYPE_FIELD } from '../../../components/expressions/expressionFieldDrag'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynSelectField } from '../../../components/forms/SynSelectField'
import { buildContextExpression, buildExpression } from '../../../utils/expressions/templateBuilder'
import { useIsVersionView } from '../VersionViewContext'

import type { KafkaPublishFormData } from './kafkaPublishFormSchema'
import { nodeHelp } from './shared/nodeFieldHelp'

const ENCODINGS = [
  { value: 'null', label: 'Null (no bytes)' },
  { value: 'utf-8', label: 'UTF-8 text' },
  { value: 'base64', label: 'Base64 binary' },
]

function droppedExpression(event: DragEvent<HTMLTextAreaElement>): string | undefined {
  try {
    const data: unknown = JSON.parse(event.dataTransfer.getData('application/json'))
    if (!isDragData(data)) return undefined
    return data.type === DRAG_TYPE_FIELD
      ? buildExpression({ nodeId: data.nodeId, fieldPath: data.fieldPath })
      : buildContextExpression(data.contextPath)
  } catch {
    return undefined
  }
}

export function KafkaPublishByteFields({
  name,
  label,
}: Readonly<{ name: 'key' | `headers.${number}`; label: string }>) {
  const { control } = useFormContext<KafkaPublishFormData>()
  const encoding = useWatch({ control, name: `${name}.encoding` })
  const readOnly = useIsVersionView()
  const isKey = name === 'key'
  const textPlaceholder = isKey ? 'Enter a message key value' : 'Enter a header value'
  const placeholder = encoding === 'base64' ? 'Enter a Base64-encoded value' : textPlaceholder
  return (
    <Stack hasGutter>
      <StackItem>
        <SynSelectField
          name={`${name}.encoding`}
          label={isKey ? 'Message key encoding' : 'Encoding'}
          ariaLabel={`${label} encoding`}
          labelHelp={isKey ? nodeHelp.kafkaPublishKeyEncoding : undefined}
          options={ENCODINGS}
          isDisabled={readOnly}
        />
      </StackItem>
      {encoding !== 'null' && (
        <StackItem>
          <SynFormField<KafkaPublishFormData, `${typeof name}.value`>
            name={`${name}.value`}
            label={isKey ? 'Message key value' : 'Value'}
            hint="Enter a value or drag an expression from the Input panel"
          >
            {({ field, fieldState, describedBy }) => (
              <TextArea
                ref={field.ref}
                id={`${name}.value`}
                name={field.name}
                aria-label={`${label} value`}
                aria-describedby={describedBy}
                value={field.value ?? ''}
                onChange={(_event, value) => field.onChange(value)}
                onBlur={field.onBlur}
                validated={fieldState.invalid ? 'error' : 'default'}
                rows={1}
                resizeOrientation="vertical"
                placeholder={placeholder}
                isDisabled={readOnly}
                onDragOver={(event) => {
                  if (!readOnly) event.preventDefault()
                }}
                onDrop={(event) => {
                  event.preventDefault()
                  if (readOnly) return
                  const expression = droppedExpression(event)
                  if (expression) field.onChange((field.value ?? '') + expression)
                }}
              />
            )}
          </SynFormField>
        </StackItem>
      )}
    </Stack>
  )
}
