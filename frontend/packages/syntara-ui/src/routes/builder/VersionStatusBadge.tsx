import { SynLabel } from '../../components/labels/SynLabel'

import type { VersionStatus } from './hooks/useVersionHistory'
export type { VersionStatus }

const statusConfig: Record<VersionStatus, { label: string; color: 'grey' | 'green' | 'teal' }> = {
  draft: { label: 'Draft', color: 'grey' },
  published: { label: 'Published', color: 'green' },
  previously_published: { label: 'Previously published', color: 'teal' },
}

export function VersionStatusBadge({ status }: Readonly<{ status: VersionStatus }>) {
  if (status === 'draft') return null
  const { label, color } = statusConfig[status]
  return <SynLabel color={color}>{label}</SynLabel>
}
