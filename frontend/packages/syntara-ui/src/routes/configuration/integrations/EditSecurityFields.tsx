import { Checkbox, ExpandableSection, HelperText, HelperTextItem, TextArea } from '@patternfly/react-core'
import { useState } from 'react'
import { useFormContext, useFormState, useWatch } from 'react-hook-form'

import { SynFormField } from '../../../components/forms/SynFormField'

import styles from './EditIntegrationForm.module.css'
import type { EditIntegrationFormValues } from './editIntegrationFormSchema'

const CA_CERT_HINT = "PEM-encoded CA certificate to trust for this integration's TLS connections."

export function EditSecurityFields() {
  const { control } = useFormContext<EditIntegrationFormValues>()
  const { errors } = useFormState({ control })
  const [userExpanded, setUserExpanded] = useState(false)
  const skipTlsVerify = useWatch<EditIntegrationFormValues, 'insecure_skip_tls_verify'>({
    name: 'insecure_skip_tls_verify',
  })
  const isExpanded = userExpanded || !!errors.ca_certificate

  return (
    <ExpandableSection
      toggleText="Security"
      isExpanded={isExpanded}
      onToggle={(_e, expanded) => setUserExpanded(expanded)}
      isIndented
    >
      <div className={styles.securityFields}>
        <SynFormField<EditIntegrationFormValues, 'allow_http'>
          name="allow_http"
          label="Allow HTTP connections"
          fieldId="edit-allow-http"
          hideFormGroupLabel
          hideFooter
        >
          {({ field }) => (
            <Checkbox
              id="edit-allow-http"
              label="Allow HTTP connections"
              description="Permits unencrypted HTTP URLs for this integration"
              isChecked={field.value}
              onChange={(_event, checked) => field.onChange(checked)}
            />
          )}
        </SynFormField>
        <SynFormField<EditIntegrationFormValues, 'insecure_skip_tls_verify'>
          name="insecure_skip_tls_verify"
          label="Disable TLS certificate verification"
          fieldId="edit-insecure-skip-tls-verify"
          hideFormGroupLabel
          hideFooter
        >
          {({ field }) => (
            <Checkbox
              id="edit-insecure-skip-tls-verify"
              label="Disable TLS certificate verification"
              description="Skips validation of the server's TLS certificate on connections"
              isChecked={field.value}
              onChange={(_event, checked) => field.onChange(checked)}
              body={
                skipTlsVerify ? (
                  <HelperText>
                    <HelperTextItem variant="warning">
                      The server's TLS certificate will not be verified. Only enable in trusted networks.
                    </HelperTextItem>
                  </HelperText>
                ) : undefined
              }
            />
          )}
        </SynFormField>
        {!skipTlsVerify && (
          <SynFormField<EditIntegrationFormValues, 'ca_certificate'>
            name="ca_certificate"
            label="CA certificate"
            fieldId="edit-ca-certificate"
            hint={CA_CERT_HINT}
          >
            {({ field, fieldState }) => (
              <TextArea
                id="edit-ca-certificate"
                placeholder={'-----BEGIN CERTIFICATE-----\n\n-----END CERTIFICATE-----'}
                aria-label="CA certificate"
                resizeOrientation="vertical"
                rows={4}
                validated={fieldState.error ? 'error' : 'default'}
                value={field.value ?? ''}
                onChange={(_event, value) => field.onChange(value || null)}
                onBlur={field.onBlur}
                name={field.name}
              />
            )}
          </SynFormField>
        )}
      </div>
    </ExpandableSection>
  )
}
