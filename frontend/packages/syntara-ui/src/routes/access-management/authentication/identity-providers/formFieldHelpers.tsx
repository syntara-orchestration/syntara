import { FormHelperText, HelperText, HelperTextItem } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { FieldError } from 'react-hook-form'

/** Re-export shared PF FormGroup label help for identity-provider forms. */
export { FieldHelpPopover, type FieldHelpPopoverProps } from '../../../../components/FieldHelpPopover'

export function FieldErrorMessage({ error }: Readonly<{ error?: FieldError }>) {
  if (!error) return null
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
          {error.message}
        </HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}

export function HintOrError({ error, hint }: Readonly<{ error?: FieldError; hint: string }>) {
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem variant={error ? 'error' : 'default'} icon={error ? <RhUiErrorIcon /> : undefined}>
          {error?.message ?? hint}
        </HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}
