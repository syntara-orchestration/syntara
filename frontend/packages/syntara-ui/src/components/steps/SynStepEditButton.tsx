import { Button, Tooltip } from '@patternfly/react-core'

import styles from './SynStepEditButton.module.css'

export function SynStepEditButton(
  props: Readonly<{
    stepTitle: string
    onClick: () => void
    className?: string
  }>
) {
  const accessibleName = `Edit ${props.stepTitle}`

  return (
    <Tooltip content="Edit step">
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
        Edit
      </Button>
    </Tooltip>
  )
}
