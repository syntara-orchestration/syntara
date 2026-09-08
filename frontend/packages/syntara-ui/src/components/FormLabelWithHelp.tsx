import { Button, Popover } from '@patternfly/react-core'

import { FieldHelpIcon } from './FieldHelpIcon'

type FormLabelWithHelpProps = {
  label: string
  helpText?: string | React.ReactNode
}

export function FormLabelWithHelp({ label, helpText }: Readonly<FormLabelWithHelpProps>) {
  const helpAriaLabel = `${label} help`

  return (
    <>
      {label}
      {helpText && (
        <Popover bodyContent={helpText} aria-label={helpAriaLabel}>
          <Button
            variant="plain"
            aria-label={helpAriaLabel}
            style={{ padding: 0, marginLeft: 'var(--pf-t--global--spacer--xs)' }}
            icon={<FieldHelpIcon />}
          />
        </Popover>
      )}
    </>
  )
}
