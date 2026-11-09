import type { AppRouteNavigationOptions } from '../../../app/routeNavigationOptions'
import * as routeRefs from '../../../app/routes/routeReferences'

export type CredentialTab = 'details' | 'workflows' | 'integrations'

export function credentialTabOptions(credentialId: string, tab: CredentialTab): AppRouteNavigationOptions {
  const params = { credentialId }
  switch (tab) {
    case 'details':
      return { to: routeRefs.credentialDetailsRoute.fullPath, params }
    case 'workflows':
      return { to: routeRefs.credentialWorkflowsRoute.fullPath, params }
    case 'integrations':
      return { to: routeRefs.credentialIntegrationsRoute.fullPath, params }
  }
}
