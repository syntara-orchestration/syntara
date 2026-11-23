import { TextArea } from '@patternfly/react-core'
import type { FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from '../../../components/forms/SynFormField'

import { CA_CERTIFICATE_HINT, CA_CERTIFICATE_PLACEHOLDER } from './caCertificate'

type CaCertificateFieldProps<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  /** RHF field name for the PEM certificate. */
  name: TName
  /** DOM id for the textarea and its form group. */
  fieldId: string
  /** Shows the required indicator and sets native `required` / `aria-required`. */
  isRequired?: boolean
}

/**
 * PEM CA certificate textarea shared by integration create and edit forms.
 * Empty input is stored as null so optional integrations omit the certificate.
 */
export function CaCertificateField<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>>({
  name,
  fieldId,
  isRequired = false,
}: Readonly<CaCertificateFieldProps<TFieldValues, TName>>) {
  return (
    <SynFormField<TFieldValues, TName>
      name={name}
      label="CA certificate"
      fieldId={fieldId}
      isRequired={isRequired}
      hint={CA_CERTIFICATE_HINT}
    >
      {({ field, fieldState, describedBy }) => (
        <TextArea
          id={fieldId}
          placeholder={CA_CERTIFICATE_PLACEHOLDER}
          aria-label="CA certificate"
          aria-describedby={describedBy}
          aria-required={isRequired ? true : undefined}
          isRequired={isRequired}
          resizeOrientation="vertical"
          rows={4}
          validated={fieldState.error ? 'error' : 'default'}
          value={typeof field.value === 'string' ? field.value : ''}
          onChange={(_event, value) => field.onChange(value === '' ? null : value)}
          onBlur={field.onBlur}
          name={field.name}
        />
      )}
    </SynFormField>
  )
}
