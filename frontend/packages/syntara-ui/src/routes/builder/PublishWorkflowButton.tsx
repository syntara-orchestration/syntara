import { Button, Icon } from '@patternfly/react-core'
import { RhUiPublishIcon } from '@patternfly/react-icons'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'

type PublishWorkflowButtonProps = Readonly<{
  canEdit: boolean
  hasNoSteps: boolean
  hasNoChanges: boolean
  validationErrorCount: number
  isVerifying: boolean
  editTooltip: string
  handleVerify: (onValid?: () => void) => void
  onPublishClick: () => void
  isNodeEditorOpen?: boolean
}>

export function PublishWorkflowButton({
  canEdit,
  hasNoSteps,
  hasNoChanges,
  validationErrorCount,
  isVerifying,
  editTooltip,
  handleVerify,
  onPublishClick,
  isNodeEditorOpen,
}: PublishWorkflowButtonProps) {
  const hasErrors = validationErrorCount > 0
  const canPublish = canEdit && !hasNoSteps && !hasErrors && !isVerifying && !hasNoChanges && !isNodeEditorOpen
  const errorSuffix = validationErrorCount === 1 ? '' : 's'

  let tooltipContent = editTooltip
  if (isNodeEditorOpen && canEdit) {
    tooltipContent = 'Finish editing the current step before publishing'
  } else if (canEdit && hasNoChanges) {
    tooltipContent = 'No changes to publish'
  } else if (canEdit && hasNoSteps) {
    tooltipContent = 'Complete your workflow before publishing'
  } else if (canEdit && isVerifying) {
    tooltipContent = 'Verifying workflow...'
  } else if (canEdit && hasErrors) {
    tooltipContent = `Verify your workflow before publishing — ${validationErrorCount} error${errorSuffix} found`
  }

  return (
    <DisabledWithTooltip isDisabled={!canPublish} content={tooltipContent} position="bottom">
      <Button
        variant="primary"
        isLoading={isVerifying}
        isAriaDisabled={!canPublish}
        onClick={canPublish ? () => handleVerify(() => onPublishClick()) : undefined}
        icon={
          <Icon isInline>
            <RhUiPublishIcon />
          </Icon>
        }
        iconPosition="start"
      >
        Publish workflow
      </Button>
    </DisabledWithTooltip>
  )
}
