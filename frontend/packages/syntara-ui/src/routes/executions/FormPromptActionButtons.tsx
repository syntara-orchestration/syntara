import { Button } from '@patternfly/react-core'

type FormPromptActionButtonsProps = Readonly<{
  isLoading?: boolean
  isDisabled?: boolean
  onRespondClick: () => void
}>

export function FormPromptActionButtons({ isLoading, isDisabled, onRespondClick }: FormPromptActionButtonsProps) {
  const disabled = isLoading || isDisabled
  return (
    <Button
      variant="primary"
      isLoading={isLoading}
      isAriaDisabled={disabled}
      onClick={disabled ? undefined : onRespondClick}
    >
      Respond to prompt
    </Button>
  )
}
