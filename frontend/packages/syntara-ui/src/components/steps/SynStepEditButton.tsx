import { Button, Tooltip } from '@patternfly/react-core'

import styles from './SynStepEditButton.module.css'

export function SynStepEditButton(
  props: Readonly<{
    stepTitle: string
    onClick: () => void
    className?: string
    /** `view` labels the button for opening the step's form read-only. */
    mode?: 'edit' | 'view'
  }>
) {
  const label = props.mode === 'view' ? 'View' : 'Edit'
  const accessibleName = `${label} ${props.stepTitle}`

  return (
    <Tooltip content={`${label} step`}>
      <Button
        variant="secondary"
        size="sm"
        aria-label={accessibleName}
        className={`nodrag nopan ${styles.editButton} ${props.className ?? ''}`}
        onClick={(event) => {
          event.stopPropagation()
          props.onClick()
        }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        {label}
      </Button>
    </Tooltip>
  )
}
