import { Button, Icon, Timestamp, Tooltip } from '@patternfly/react-core'
import { RhUiSaveFillIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { toDisplayDate } from '../../utils/dateUtils'

type SaveWorkflowButtonProps = Readonly<{
  isPending: boolean
  isDirty: boolean
  isNew: boolean
  lastSavedAt?: string | null
  onSave: () => void
  canEdit: boolean
  editTooltip: string
  isNodeEditorOpen?: boolean
}>

export function SaveWorkflowButton({
  isPending,
  isDirty,
  isNew,
  lastSavedAt,
  onSave,
  canEdit,
  editTooltip,
  isNodeEditorOpen,
}: SaveWorkflowButtonProps) {
  const isDisabled = !canEdit || isPending || (!isDirty && !isNew) || !!isNodeEditorOpen
  const lastSavedDate = toDisplayDate(lastSavedAt)
  const lastSavedText = lastSavedDate ? (
    <>
      Last saved <Timestamp date={lastSavedDate} dateFormat="medium" timeFormat="medium" />
    </>
  ) : null

  let disabledTooltip: ReactNode
  if (!canEdit) {
    disabledTooltip = editTooltip
  } else if (isNodeEditorOpen && lastSavedText) {
    disabledTooltip = (
      <>
        Finish editing the current step before saving
        <br />
        {lastSavedText}
      </>
    )
  } else if (isNodeEditorOpen) {
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
      {isPending ? 'Saving...' : 'Save'}
    </Button>
  )

  if (isDisabled) {
    return (
      <DisabledWithTooltip isDisabled content={disabledTooltip} position="bottom">
        {button}
      </DisabledWithTooltip>
    )
  }

  return (
    <Tooltip content={enabledTooltip} position="bottom" enableFlip={false}>
      {button}
    </Tooltip>
  )
}
