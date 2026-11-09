import { FormHelperText, HelperText, HelperTextItem } from '@patternfly/react-core'

import * as routeRefs from '../../../app/routes/routeReferences'
import { SynLink } from '../../../components/SynLink'
import { useIntegrationPermissions } from '../../configuration/integrations/useIntegrationPermissions'

export type IntegrationRequiredHelperProps = Readonly<{
  integrationLabel: string
  actionLabel: string
}>

export function IntegrationRequiredHelper({ integrationLabel, actionLabel }: IntegrationRequiredHelperProps) {
  const { canCreate } = useIntegrationPermissions()

  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem>
          An administrator must{' '}
          {canCreate ? (
            <SynLink options={{ to: routeRefs.configureIntegrationRoute.fullPath }}>
              configure {integrationLabel}
            </SynLink>
          ) : (
            `configure ${integrationLabel}`
          )}{' '}
          before {actionLabel}.
        </HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}
