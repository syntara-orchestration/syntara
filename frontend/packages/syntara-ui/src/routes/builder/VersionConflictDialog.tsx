import { Button, Content, List, ListItem, Modal, ModalBody, ModalFooter, ModalHeader } from '@patternfly/react-core'

import { useBlurOnOpen } from '../../hooks/useBlurOnOpen'

import { formatHistoryDateTime } from './historyDateUtils'

export type ConflictAction = 'save' | 'publish' | 'run'

export type ConflictInfo = {
  currentVersion: number
  currentVersionName: string | null
  expectedVersion: number
  expectedVersionName: string | null
  expectedVersionCreatedAt: string | null
  createdByUsername: string
  createdAt: string
}

type VersionConflictDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  conflictAction: ConflictAction
  conflictInfo?: ConflictInfo | null
  onSaveAsNewest: (action: ConflictAction) => void
  onDuplicate: (action: ConflictAction) => void
  onRefreshToLatest: () => void
  isLoading?: boolean
}>

const COPY = {
  save: {
    title: 'Save conflict: newer version available',
    primaryLabel: 'Save as newest version',
    duplicateLabel: 'Create duplicate workflow with this version',
    primaryBullet: 'Save as newest version: Save this version as the newest version of the workflow.',
    duplicateBullet:
      'Create duplicate workflow with this version: Create and save a completely separate workflow containing your current changes. This allows you to preserve your work without affecting the existing version.',
  },
  publish: {
    title: 'Publish conflict: newer version available',
    primaryLabel: 'Publish as newest version',
    duplicateLabel: 'Create duplicate workflow with this version and publish',
    primaryBullet: 'Publish as newest version: Save this version as the newest version of the workflow.',
    duplicateBullet:
      'Create duplicate workflow with this version and publish: Create a completely separate workflow containing your current changes and publish that workflow. This allows you to preserve your work without affecting the existing version.',
  },
  run: {
    title: 'Run conflict: newer version available',
    primaryLabel: 'Run as newest version',
    duplicateLabel: 'Create duplicate workflow with this version and run',
    primaryBullet:
      'Overwrite existing: Replace the current version on the server with your changes. The intermediate edits made by the other user can be found in another version of this workflow in the version history.',
    duplicateBullet:
      'Create duplicate workflow with this version and run: Create a completely separate workflow containing your current changes and run that workflow. This allows you to preserve your work without affecting the existing version.',
  },
} as const

function getVersionLabel(
  name: string | null | undefined,
  dateIso: string | null | undefined,
  version: number | undefined
): string {
  if (name) return name
  if (dateIso) return formatHistoryDateTime(dateIso)
  if (version != null) return String(version)
  return ''
}

/**
 * Version conflict resolution dialog.
 *
 * Uses a plain PF Modal instead of SynConfirmationDialog because the conflict
 * resolution flow requires three distinct actions (save as newest, duplicate,
 * refresh to latest), which does not fit SynConfirmationDialog's two-button
 * (confirm + cancel) model.
 */
export function VersionConflictDialog({
  isOpen,
  onClose,
  conflictAction,
  conflictInfo,
  onSaveAsNewest,
  onDuplicate,
  onRefreshToLatest,
  isLoading = false,
}: VersionConflictDialogProps) {
  useBlurOnOpen(isOpen)
  const copy = COPY[conflictAction]

  const currentVersionLabel = getVersionLabel(
    conflictInfo?.currentVersionName,
    conflictInfo?.createdAt,
    conflictInfo?.currentVersion
  )
  const expectedVersionLabel = getVersionLabel(
    conflictInfo?.expectedVersionName,
    conflictInfo?.expectedVersionCreatedAt,
    conflictInfo?.expectedVersion
  )

  return (
    <Modal isOpen={isOpen} onClose={onClose} variant="medium" aria-label={copy.title}>
      <ModalHeader title={copy.title} titleIconVariant="warning" />
      <ModalBody>
        {conflictInfo && (
          <Content component="p">
            Version <strong>{currentVersionLabel}</strong> was saved by {conflictInfo.createdByUsername}. Your changes
            are based on version <strong>{expectedVersionLabel}</strong>.
          </Content>
        )}
        <Content component="p">
          A newer version of this workflow has been saved by another user since you began editing. To prevent data loss,
          please choose how you would like to proceed:
        </Content>
        <List>
          <ListItem>{copy.primaryBullet}</ListItem>
          <ListItem>{copy.duplicateBullet}</ListItem>
          <ListItem>
            Refresh to latest: Discard your current unsaved changes and reload the workflow to show the most up-to-date
            version.
          </ListItem>
        </List>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={() => onSaveAsNewest(conflictAction)}
          isDisabled={isLoading}
          isLoading={isLoading}
        >
          {copy.primaryLabel}
        </Button>
        <Button variant="secondary" onClick={() => onDuplicate(conflictAction)} isDisabled={isLoading}>
          {copy.duplicateLabel}
        </Button>
        <Button variant="link" onClick={onRefreshToLatest} isDisabled={isLoading}>
          Refresh to latest
        </Button>
      </ModalFooter>
    </Modal>
  )
}
