import { FormGroup, FormHelperText, HelperText, HelperTextItem, TextArea } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { Controller, type useForm } from 'react-hook-form'

import type { EditIntegrationFormValues } from './editIntegrationFormSchema'
import { integrationHelp } from './integrationFieldHelp'
import { KafkaSaslMechanismField } from './kafkaSaslField'

export function EditBootstrapServersField({
  control,
  errorMessage,
}: Readonly<{
  control: ReturnType<typeof useForm<EditIntegrationFormValues>>['control']
  errorMessage: string | undefined
}>) {
  return (
    <FormGroup
      label="Bootstrap servers"
      isRequired
      fieldId="edit-bootstrap-servers"
      labelHelp={integrationHelp.kafkaBootstrapServers}
    >
      <Controller
        name="bootstrap_servers"
        control={control}
        render={({ field }) => (
          <TextArea
            id="edit-bootstrap-servers"
            aria-label="Bootstrap servers"
            aria-required
            resizeOrientation="vertical"
            rows={4}
            validated={errorMessage ? 'error' : 'default'}
            value={field.value ?? ''}
            onChange={(_event, value) => field.onChange(value)}
            onBlur={field.onBlur}
            name={field.name}
          />
        )}
      />
      {errorMessage && (
        <FormHelperText>
          <HelperText>
            <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
              {errorMessage}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      )}
    </FormGroup>
  )
}

export function EditKafkaFields({
  control,
  errorMessage,
}: Readonly<{
  control: ReturnType<typeof useForm<EditIntegrationFormValues>>['control']
  errorMessage: string | undefined
}>) {
  return (
    <>
      <EditBootstrapServersField control={control} errorMessage={errorMessage} />
      <KafkaSaslMechanismField control={control} name="sasl_mechanism" fieldId="edit-sasl-mechanism" />
    </>
  )
}
