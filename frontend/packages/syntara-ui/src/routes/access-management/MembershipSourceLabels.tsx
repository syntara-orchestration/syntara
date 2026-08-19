import { Flex, FlexItem } from '@patternfly/react-core'

import { NxLabel } from '../../components/labels/NxLabel'

import type { MembershipSourceInfo } from './membershipSourceUtils'

export function MembershipSourceLabels({ sources }: Readonly<{ sources?: MembershipSourceInfo[] }>) {
  if (!sources || sources.length === 0) return null
  return (
    <Flex gap={{ default: 'gapXs' }} flexWrap={{ default: 'wrap' }}>
      {sources.map((s, idx) => (
        <FlexItem key={`${s.type}-${s.provider_name ?? idx}`}>
          <NxLabel color={s.type === 'idp' ? 'blue' : 'grey'}>
            {s.type === 'idp' ? (s.provider_name ?? 'IdP') : 'Manual'}
          </NxLabel>
        </FlexItem>
      ))}
    </Flex>
  )
}
