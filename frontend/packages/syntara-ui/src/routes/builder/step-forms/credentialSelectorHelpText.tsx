import { List, ListItem } from '@patternfly/react-core'

/**
 * Shared help text content for the CredentialSelector popover across step forms.
 */
export function credentialHelpText(introText: string) {
  return (
    <>
      {introText}
      <List isPlain style={{ marginTop: 'var(--pf-t--global--spacer--sm)' }}>
        <ListItem>Credentials are encrypted and never exposed in logs or workflow definitions</ListItem>
        <ListItem>You can create a new credential directly from this dropdown</ListItem>
        <ListItem>Manage credentials in Configuration &rarr; Credentials</ListItem>
      </List>
    </>
  )
}
