import { FlexItem } from '@patternfly/react-core'

import { NxLabel } from '../../components/labels/NxLabel'
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
          <NxLabel color="grey">
            Viewing <ExecutionTimestamp dateString={viewedVersionDate} />
          </NxLabel>
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
