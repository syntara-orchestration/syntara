import { Button, Content, ContentVariants, Flex, FlexItem, Tooltip } from '@patternfly/react-core'
import { RhUiDislikeIcon, RhUiLikeIcon } from '@patternfly/react-icons'

export type ApprovalsBulkActionsProps = {
  selectedCount: number
  onApprove: () => void
  onReject: () => void
  isDisabled?: boolean
  /** When set, buttons are aria-disabled with this tooltip explaining the missing permission. */
  permissionTooltip?: string
}

export function ApprovalsBulkActions({
  selectedCount,
  onApprove,
  onReject,
  isDisabled = false,
  permissionTooltip: permTooltip,
}: Readonly<ApprovalsBulkActionsProps>) {
  const hasSelection = selectedCount > 0
  const permDenied = !!permTooltip
  const disabled = isDisabled || !hasSelection || permDenied

  let tooltipContent: string | undefined
  if (permDenied) {
    tooltipContent = permTooltip
  } else if (!hasSelection) {
    tooltipContent = 'At least one approval needs to be selected to take action'
  }

  const approveButton = (
    <Button
      icon={<RhUiLikeIcon />}
      variant="secondary"
      isAriaDisabled={permDenied}
      isDisabled={!permDenied && disabled}
      onClick={disabled ? undefined : onApprove}
    >
      Approve
    </Button>
  )

  const rejectButton = (
    <Button
      icon={<RhUiDislikeIcon />}
      variant="secondary"
      isDanger
      isAriaDisabled={permDenied}
      isDisabled={!permDenied && disabled}
      onClick={disabled ? undefined : onReject}
    >
      Reject
    </Button>
  )

  return (
    <Flex
      role="toolbar"
      aria-label={hasSelection ? `${selectedCount} selected` : 'Approval actions'}
      gap={{ default: 'gapMd' }}
      alignItems={{ default: 'alignItemsCenter' }}
    >
      {hasSelection && (
        <FlexItem>
          <Content component={ContentVariants.p}>{selectedCount} selected</Content>
        </FlexItem>
      )}
      <FlexItem>
        {tooltipContent ? <Tooltip content={tooltipContent}>{approveButton}</Tooltip> : approveButton}
      </FlexItem>
      <FlexItem>{tooltipContent ? <Tooltip content={tooltipContent}>{rejectButton}</Tooltip> : rejectButton}</FlexItem>
    </Flex>
  )
}
