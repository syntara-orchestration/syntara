import { FormHelperText, HelperText, HelperTextItem, Switch } from '@patternfly/react-core'

import { FieldHelpPopover } from '../../../../components/FieldHelpPopover'
import { SynFormField } from '../../../../components/forms/SynFormField'
import { SynSwitchField } from '../../../../components/forms/SynSwitchField'
import { SynTextField } from '../../../../components/forms/SynTextField'

import { type IdentityProviderFormData } from './identityProviderFormSchema'
import { ManualEndpointFields } from './ManualEndpointFields'

export function ConnectionFields({ autoDiscovery, isEdit }: Readonly<{ autoDiscovery: boolean; isEdit?: boolean }>) {
  return (
    <>
      <SynTextField
        name="issuerUrl"
        label="Issuer URL"
        fieldId="issuer-url"
        isRequired
        placeholder="https://accounts.google.com"
        labelHelp={
          <FieldHelpPopover helpText="The base URL of your OpenID Connect provider. Used to discover endpoints automatically." />
        }
      />

      <SynSwitchField
        name="autoDiscovery"
        label="Use OIDC Discovery"
        fieldId="auto-discovery"
        hint="Most providers support this. When enabled, you only need the Issuer URL — all other endpoints are detected automatically."
      />

      {!autoDiscovery && <ManualEndpointFields />}

      <SynTextField
        name="clientId"
        label="Client ID"
        fieldId="client-id"
        isRequired
        placeholder="your-client-id"
        labelHelp={
          <FieldHelpPopover helpText="The OAuth 2.0 client identifier registered with your identity provider." />
        }
      />

      <SynTextField
        name="clientSecret"
        label="Client secret"
        fieldId="client-secret"
        isRequired={!isEdit}
        type="password"
        autoComplete="off"
        placeholder={isEdit ? 'Enter new secret to update' : 'your-client-secret'}
        labelHelp={
          <FieldHelpPopover helpText="The OAuth 2.0 client secret used to authenticate with the identity provider." />
        }
        hint={isEdit ? 'Leave empty to keep the existing secret. Enter a new value to update it.' : undefined}
      />

      <SynFormField<IdentityProviderFormData, 'disableTlsVerify'>
        name="disableTlsVerify"
        label="Disable TLS certificate verification"
        fieldId="disable-tls-verify"
        hideFormGroupLabel
        hideFooter
      >
        {({ field }) => (
          <>
            <Switch
              id="disable-tls-verify"
              label="Disable TLS certificate verification"
              hasCheckIcon
              isChecked={field.value}
              onChange={(_event, checked) => field.onChange(checked)}
            />
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant="warning">
                  When enabled, TLS certificate errors are ignored for all requests to this identity provider. Only use
                  this for testing or when connecting to providers with self-signed certificates.
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          </>
        )}
      </SynFormField>
    </>
  )
}
