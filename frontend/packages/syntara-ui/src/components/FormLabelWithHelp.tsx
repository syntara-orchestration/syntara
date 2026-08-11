import { Button, Popover } from '@patternfly/react-core'

import { FieldHelpIcon } from './FieldHelpIcon'

type FormLabelWithHelpProps = {
  label: string
  helpText?: string | React.ReactNode
}

export function FormLabelWithHelp({ label, helpText }: Readonly<FormLabelWithHelpProps>) {
  return (
    <>
      {label}
      {helpText && (
        <Popover bodyContent={helpText}>
          <Button
            variant="plain"
            aria-label={`${label} help`}
            style={{ padding: 0, marginLeft: 'var(--pf-t--global--spacer--xs)' }}
            icon={<FieldHelpIcon />}
          />
        </Popover>
      )}
    </>
  )
}
