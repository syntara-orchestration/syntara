import { FieldHelpPopover } from '../../../../components/FieldHelpPopover'
import { SynTextField } from '../../../../components/forms/SynTextField'

export function ManualEndpointFields() {
  return (
    <>
      <SynTextField
        name="authorizationEndpoint"
        label="Authorization endpoint"
        fieldId="authorization-endpoint"
        isRequired
        placeholder="https://provider.com/oauth2/authorize"
        labelHelp={
          <FieldHelpPopover helpText="URL where users are redirected to authenticate with the identity provider." />
        }
      />
      <SynTextField
        name="tokenEndpoint"
        label="Token endpoint"
        fieldId="token-endpoint"
        isRequired
        placeholder="https://provider.com/oauth2/token"
        labelHelp={<FieldHelpPopover helpText="URL where authorization codes are exchanged for tokens." />}
      />
      <SynTextField
        name="jwksUri"
        label="JWKS URI"
        fieldId="jwks-uri"
        isRequired
        placeholder="https://provider.com/oauth2/keys"
        labelHelp={<FieldHelpPopover helpText="URL to fetch public keys for token signature verification." />}
      />
      <SynTextField
        name="userinfoEndpoint"
        label="Userinfo endpoint"
        fieldId="userinfo-endpoint"
        placeholder="https://provider.com/oauth2/userinfo"
        labelHelp={<FieldHelpPopover helpText="URL to fetch additional user claims (optional)." />}
      />
      <SynTextField
        name="endSessionEndpoint"
        label="End session endpoint"
        fieldId="end-session-endpoint"
        placeholder="https://provider.com/oauth2/logout"
        labelHelp={
          <FieldHelpPopover helpText="URL for single logout — users are redirected here on sign-out (optional)." />
        }
      />
    </>
  )
}
