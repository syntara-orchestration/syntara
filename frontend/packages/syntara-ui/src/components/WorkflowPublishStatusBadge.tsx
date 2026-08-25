import { SynLabel } from './labels/SynLabel'
import { derivePublishStatus, type PublishDisplayStatus } from './publishStatusUtils'

type BadgeConfig = {
  color: 'green' | 'grey' | 'yellow'
  label: string
}

const publishBadgeConfig: Record<PublishDisplayStatus, BadgeConfig> = {
  published: { color: 'green', label: 'Published' },
  unpublished: { color: 'grey', label: 'Draft' },
  unpublished_changes: { color: 'yellow', label: 'Unpublished changes' },
}

type WorkflowPublishStatusBadgeProps = Readonly<{
  publishedVersionId: string | null | undefined
  currentVersionId?: string | null
  hasUnpublishedChanges?: boolean
}>

export function WorkflowPublishStatusBadge({
  publishedVersionId,
  currentVersionId,
  hasUnpublishedChanges,
}: WorkflowPublishStatusBadgeProps) {
  const displayStatus =
    hasUnpublishedChanges && publishedVersionId != null
      ? 'unpublished_changes'
      : derivePublishStatus(publishedVersionId, currentVersionId)
  const { color, label } = publishBadgeConfig[displayStatus]

  return <SynLabel color={color}>{label}</SynLabel>
}
