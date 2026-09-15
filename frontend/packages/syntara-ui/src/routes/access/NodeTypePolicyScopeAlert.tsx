import { Alert } from '@patternfly/react-core'

import { NODE_TYPE_POLICY_SYSTEM_SCOPE_MESSAGE } from './nodeTypePolicyUtils'

type NodeTypePolicyScopeAlertProps = {
  visible: boolean
}

export function NodeTypePolicyScopeAlert({ visible }: Readonly<NodeTypePolicyScopeAlertProps>) {
  if (!visible) return null
  return <Alert variant="info" isInline title={NODE_TYPE_POLICY_SYSTEM_SCOPE_MESSAGE} />
}
