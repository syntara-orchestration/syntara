import { FormGroup, FormHelperText, HelperText, HelperTextItem, TextArea } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { Controller, useWatch, type useForm } from 'react-hook-form'

import type { EditIntegrationFormValues } from './editIntegrationFormSchema'
import { integrationHelp } from './integrationFieldHelp'
import { KafkaSaslMechanismField } from './kafkaSaslField'
import { KafkaTransportFields } from './KafkaTransportFields'

function EditBootstrapServersField({
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
            aria-invalid={Boolean(errorMessage)}
            aria-describedby={errorMessage ? 'edit-bootstrap-servers-error' : undefined}
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
            <HelperTextItem id="edit-bootstrap-servers-error" icon={<RhUiErrorIcon />} variant="error">
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
  const protocol = useWatch({ control, name: 'security_protocol' }) ?? 'SASL_SSL'
  return (
    <>
      <EditBootstrapServersField control={control} errorMessage={errorMessage} />
      <KafkaTransportFields
        control={control}
        protocolName="security_protocol"
        plaintextName="allow_plaintext"
        fieldId="edit-security-protocol"
      />
      {protocol === 'SASL_SSL' && (
        <KafkaSaslMechanismField control={control} name="sasl_mechanism" fieldId="edit-sasl-mechanism" />
      )}
    </>
  )
}
