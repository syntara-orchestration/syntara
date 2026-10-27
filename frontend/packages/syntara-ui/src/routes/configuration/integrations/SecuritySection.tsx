import { DescriptionList, StackItem, Title } from '@patternfly/react-core'
import { RhUiWarningIcon } from '@patternfly/react-icons'

import { SynDetail } from '../../../components/details/SynDetail'
import { SynLabel } from '../../../components/labels/SynLabel'

import styles from './IntegrationDetail.module.css'
import type { IntegrationRead } from './integrationTypes'

export function SecuritySection({
  configuration,
}: Readonly<{
  configuration: IntegrationRead['configuration']
}>) {
  if (!configuration || !('allow_http' in configuration) || !('insecure_skip_tls_verify' in configuration)) {
    return null
  }

  const kafkaProtocol =
    configuration.integration_type === 'kafka' ? (configuration.security_protocol ?? 'SASL_SSL') : null

  return (
    <StackItem>
      <Title headingLevel="h2" size="lg">
        Security
      </Title>
      <DescriptionList isHorizontal className={styles.securityDetails}>
        {kafkaProtocol ? (
          <SynDetail label="Security protocol">{kafkaProtocol}</SynDetail>
        ) : (
          <SynDetail label="HTTP connections">
            {configuration.allow_http ? (
              <SynLabel variant="outline" status="warning" icon={<RhUiWarningIcon />}>
                HTTP allowed
              </SynLabel>
            ) : (
              'HTTPS only'
            )}
          </SynDetail>
        )}
        {kafkaProtocol !== 'PLAINTEXT' && (
          <SynDetail label="TLS certificate verification">
            {configuration.insecure_skip_tls_verify ? (
              <SynLabel variant="outline" status="warning" icon={<RhUiWarningIcon />}>
                TLS verification disabled
              </SynLabel>
            ) : (
              'Enabled'
            )}
          </SynDetail>
        )}
      </DescriptionList>
    </StackItem>
  )
}
