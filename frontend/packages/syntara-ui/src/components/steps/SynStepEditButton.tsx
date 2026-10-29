import { Button, Tooltip } from '@patternfly/react-core'

import styles from './SynStepEditButton.module.css'

export function SynStepEditButton(
  props: Readonly<{
    stepTitle: string
    onClick: () => void
    className?: string
  }>
) {
  const label = `Edit ${props.stepTitle}`

  return (
    <Tooltip content={label}>
      <Button
        variant="secondary"
        size="sm"
        aria-label={label}
        className={`nodrag nopan ${styles.editButton} ${props.className ?? ''}`}
        onClick={(event) => {
          event.stopPropagation()
          props.onClick()
        }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        Edit
      </Button>
    </Tooltip>
  )
}
