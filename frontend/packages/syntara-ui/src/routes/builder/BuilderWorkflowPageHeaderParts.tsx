import { FlexItem } from '@patternfly/react-core'

import { SynLabel } from '../../components/labels/SynLabel'
import { ExecutionTimestamp } from '../../components/table/ExecutionTimestamp'

import { isVersionStatus } from './hooks/useVersionHistory'
import { VersionStatusBadge } from './VersionStatusBadge'

export function BuilderVersionViewTitleRowAddons({
  viewedVersionDate,
  viewedVersionStatus,
}: Readonly<{
  viewedVersionDate?: string | null
  viewedVersionStatus?: string | null
}>) {
  return (
    <>
      {viewedVersionDate ? (
        <FlexItem>
          <SynLabel color="grey">
            Viewing <ExecutionTimestamp dateString={viewedVersionDate} />
          </SynLabel>
        </FlexItem>
      ) : null}
      {viewedVersionStatus && isVersionStatus(viewedVersionStatus) ? (
        <FlexItem>
          <VersionStatusBadge status={viewedVersionStatus} />
        </FlexItem>
      ) : null}
    </>
  )
}
