import {
  Button,
  Flex,
  FlexItem,
  FormSection,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useRef } from 'react'
import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'

import { FormFieldError } from '../../../components/FormFieldError'
import { SynSelectField } from '../../../components/forms/SynSelectField'
import { SynTextAreaField } from '../../../components/forms/SynTextAreaField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { useIsVersionView } from '../VersionViewContext'

import { KAFKA_MAX_HEADERS, type KafkaPublishFormData } from './kafkaPublishFormSchema'

const ENCODINGS = [
  { value: 'null', label: 'Null (no bytes)' },
  { value: 'utf-8', label: 'UTF-8 text' },
  { value: 'base64', label: 'Base64 binary' },
]
const HEADER_SOURCES = [
  { value: 'entries', label: 'Ordered entries' },
  { value: 'template', label: 'Full-value template' },
]

function ByteFields({ name, label }: Readonly<{ name: 'key' | `headers.${number}`; label: string }>) {
  const { control } = useFormContext<KafkaPublishFormData>()
  const encoding = useWatch({ control, name: `${name}.encoding` })
  const readOnly = useIsVersionView()
  return (
    <Stack hasGutter>
      <StackItem>
        <SynSelectField
          name={`${name}.encoding`}
          label={`${label} encoding`}
          options={ENCODINGS}
          isDisabled={readOnly}
          hint={name === 'key' ? 'Null has no bytes. An empty UTF-8 or Base64 value is empty bytes.' : undefined}
        />
      </StackItem>
      {encoding !== 'null' && (
        <StackItem>
          <SynTextAreaField
            name={`${name}.value`}
            label={`${label} value`}
            rows={2}
            isDisabled={readOnly}
            hint={'Text or standard Base64, without JSON quotes. Templates must resolve to strings.'}
          />
        </StackItem>
      )}
    </Stack>
  )
}

export function KafkaPublishMessageFields() {
  const {
    control,
    setFocus,
    formState: { errors },
  } = useFormContext<KafkaPublishFormData>()
  const { fields, append, remove, move } = useFieldArray({ control, name: 'headers' })
  const source = useWatch({ control, name: 'headers_mode' })
  const readOnly = useIsVersionView()
  const addButtonRef = useRef<HTMLButtonElement>(null)

  function removeHeader(index: number) {
    if (fields.length === 1) addButtonRef.current?.focus()
    else setFocus(`headers.${index === 0 ? 1 : index - 1}.name`)
    remove(index)
  }

  function moveHeader(index: number, destination: number) {
    setFocus(`headers.${index}.name`)
    move(index, destination)
  }
  return (
    <Stack hasGutter>
      <StackItem>
        <FormSection title="Message key" titleElement="h3">
          <ByteFields name="key" label="Message key" />
        </FormSection>
      </StackItem>
      <StackItem>
        <FormSection title="Message headers" titleElement="h3">
          <SynSelectField name="headers_mode" label="Header source" options={HEADER_SOURCES} isDisabled={readOnly} />
          <HelperText>
            <HelperTextItem>
              Headers retain their order. Repeated names, null values, and empty bytes are supported. Maximum 128
              entries.
            </HelperTextItem>
          </HelperText>
          {source === 'template' ? (
            <SynTextAreaField
              name="headers_template"
              label="Headers template"
              rows={3}
              isDisabled={readOnly}
              hint={
                'Use a full-value template such as ${trigger.payload.headers}. It must resolve to an ordered list of {name, value} entries; values are null or {encoding, value} objects.'
              }
            />
          ) : (
            <Stack hasGutter>
              {fields.map((field, index) => (
                <StackItem key={field.id}>
                  <FormSection
                    title={`Header ${String(index + 1)}`}
                    titleElement="h4"
                    role="group"
                    aria-label={`Header ${String(index + 1)}`}
                  >
                    <SynTextField
                      name={`headers.${index}.name`}
                      label={`Header ${String(index + 1)} name`}
                      isDisabled={readOnly}
                    />
                    <ByteFields name={`headers.${index}`} label={`Header ${String(index + 1)}`} />
                    {!readOnly && (
                      <Flex>
                        <FlexItem>
                          <Button
                            type="button"
                            variant="link"
                            isDisabled={index === 0}
                            aria-label={`Move header ${String(index + 1)} up`}
                            onClick={() => moveHeader(index, index - 1)}
                          >
                            Move up
                          </Button>
                        </FlexItem>
                        <FlexItem>
                          <Button
                            type="button"
                            variant="link"
                            isDisabled={index === fields.length - 1}
                            aria-label={`Move header ${String(index + 1)} down`}
                            onClick={() => moveHeader(index, index + 1)}
                          >
                            Move down
                          </Button>
                        </FlexItem>
                        <FlexItem>
                          <Button
                            type="button"
                            variant="link"
                            icon={<RhUiTrashIcon />}
                            aria-label={`Remove header ${String(index + 1)}`}
                            onClick={() => removeHeader(index)}
                          >
                            Remove
                          </Button>
                        </FlexItem>
                      </Flex>
                    )}
                  </FormSection>
                </StackItem>
              ))}
              <StackItem>
                <FormFieldError message={errors.headers?.root?.message ?? errors.headers?.message} />
              </StackItem>
              {!readOnly && (
                <StackItem>
                  <Button
                    ref={addButtonRef}
                    type="button"
                    variant="link"
                    icon={<RhUiAddIcon />}
                    isDisabled={fields.length >= KAFKA_MAX_HEADERS}
                    onClick={() =>
                      append({ name: '', encoding: 'utf-8', value: '' }, { focusName: `headers.${fields.length}.name` })
                    }
                  >
                    Add header
                  </Button>
                </StackItem>
              )}
            </Stack>
          )}
        </FormSection>
      </StackItem>
    </Stack>
  )
}
