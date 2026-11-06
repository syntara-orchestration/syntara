import { SynListPanelView } from '../../components/panels/list/SynListPanel'
import { CheckAccessTab } from '../access/CheckAccessTab'

import { TokenRevocationTab } from './token-revocation/TokenRevocation'

const noop = () => {}

export function AccessManagementCheckAccessRoute() {
  return (
    <SynListPanelView
      tabKey="check-access"
      tabLabel="Check access"
      isPending={false}
      error={null}
      isEmpty={false}
      hasActiveFilters={false}
      onRetry={noop}
      onClearAllFilters={noop}
      body={<CheckAccessTab />}
    />
  )
}

export function AccessManagementTokenRevocationRoute() {
  return (
    <SynListPanelView
      tabKey="token-revocation"
      tabLabel="Token revocation"
      isPending={false}
      error={null}
      isEmpty={false}
      hasActiveFilters={false}
      onRetry={noop}
      onClearAllFilters={noop}
      body={<TokenRevocationTab />}
    />
  )
}
