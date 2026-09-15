import { Flex, FlexItem } from '@patternfly/react-core'

import { SynLabel } from '../../components/labels/SynLabel'

import type { MembershipSourceInfo } from './membershipSourceUtils'

export function MembershipSourceLabels({ sources }: Readonly<{ sources?: MembershipSourceInfo[] }>) {
  if (!sources || sources.length === 0) return null
  return (
    <Flex gap={{ default: 'gapXs' }} flexWrap={{ default: 'wrap' }}>
      {sources.map((s, idx) => (
        <FlexItem key={`${s.type}-${s.provider_name ?? idx}`}>
          <SynLabel color={s.type === 'idp' ? 'blue' : 'grey'}>
            {s.type === 'idp' ? (s.provider_name ?? 'IdP') : 'Manual'}
          </SynLabel>
        </FlexItem>
      ))}
    </Flex>
  )
}
