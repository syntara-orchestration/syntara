import { Content, ContentVariants } from '@patternfly/react-core'

import styles from './CredentialFormModal.module.css'

export const CREDENTIAL_TYPE_HELP = (
  <Content>
    <Content component={ContentVariants.p} className={styles.credentialTypeHelpText}>
      Select the type of credential based on the authentication method required:
    </Content>
    <Content component="ul">
      <Content component="li">
        <strong>Kafka-connection</strong> &ndash; For a Kafka connection username and password
      </Content>
      <Content component="li">
        <strong>HTTP Bearer Token</strong> &ndash; For APIs using bearer token authentication
      </Content>
      <Content component="li">
        <strong>HTTP Basic Auth</strong> &ndash; For APIs using username/password authentication
      </Content>
      <Content component="li">
        <strong>SSH Key</strong> &ndash; For SSH connections to remote servers
      </Content>
      <Content component="li">
        <strong>LLM Provider</strong> &ndash; For AI/LLM service API keys
      </Content>
      <Content component="li">
        <strong>Ansible Automation Platform</strong> &ndash; For AAP API access
      </Content>
    </Content>
  </Content>
)
