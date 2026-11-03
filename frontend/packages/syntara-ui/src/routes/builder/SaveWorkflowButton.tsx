import { Button, Icon, Timestamp, Tooltip } from '@patternfly/react-core'
import { RhUiSaveFillIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'

import { toDisplayDate } from '../../utils/dateUtils'

import styles from './SaveWorkflowButton.module.css'

type SaveWorkflowButtonProps = Readonly<{
  isPending: boolean
  isDirty: boolean
  isNew: boolean
  lastSavedAt?: string | null
  onSave: () => void
  canEdit: boolean
  editTooltip: string
  isStepEditorOpen?: boolean
}>

export function SaveWorkflowButton({
  isPending,
  isDirty,
  isNew,
  lastSavedAt,
  onSave,
  canEdit,
  editTooltip,
  isStepEditorOpen,
}: SaveWorkflowButtonProps) {
  const isDisabled = !canEdit || isPending || (!isDirty && !isNew) || !!isStepEditorOpen
  const lastSavedDate = toDisplayDate(lastSavedAt)
  const lastSavedText = lastSavedDate ? (
    <>
      Last saved:{' '}
      <span className={styles.lastSavedTooltip}>
        <Timestamp date={lastSavedDate} dateFormat="medium" timeFormat="medium" />
      </span>
    </>
  ) : null

  let disabledTooltip: ReactNode
  if (!canEdit) {
    disabledTooltip = editTooltip
  } else if (isStepEditorOpen && lastSavedText) {
    disabledTooltip = (
      <>
        Finish editing the current step before saving
        <br />
        {lastSavedText}
      </>
    )
  } else if (isStepEditorOpen) {
    disabledTooltip = 'Finish editing the current step before saving'
  } else {
    disabledTooltip = lastSavedText ?? 'Save workflow'
  }

  const enabledTooltip = lastSavedText ?? 'Save workflow'

  const button = (
    <Button
      variant="plain"
      onClick={!isDisabled ? onSave : undefined}
      isLoading={isPending}
      isAriaDisabled={isDisabled}
      icon={
        <Icon isInline>
          <RhUiSaveFillIcon />
        </Icon>
      }
      iconPosition="start"
    >
      {isPending ? 'Saving...' : 'Save workflow'}
    </Button>
  )

  // Keep a single Tooltip wrapper so pending/clean transitions do not remount the button tree.
  return (
    <Tooltip content={isDisabled ? disabledTooltip : enabledTooltip} position="bottom" enableFlip={false}>
      {button}
    </Tooltip>
  )
}
