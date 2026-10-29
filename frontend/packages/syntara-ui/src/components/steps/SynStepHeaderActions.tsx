import { Flex, FlexItem } from '@patternfly/react-core'
import type { ComponentProps } from 'react'

import type { StepMenuAction } from '../../routes/workflows/canvas/nodes/hooks/useStepMenuActions'

import { SynStepEditButton } from './SynStepEditButton'
import { SynStepExpandToggle } from './SynStepExpandToggle'
import actionsStyles from './SynStepHeaderActions.module.css'
import { SynStepMenu } from './SynStepMenu'

export function SynStepHeaderActions(
  props: Readonly<{
    stepTitle: string
    menuActions?: StepMenuAction[]
    expandable?: boolean
    showMenuActions: boolean
    menuClassName?: string
    menuPopperProps?: ComponentProps<typeof SynStepMenu>['popperProps']
  }>
) {
  const menuActions = props.menuActions ?? []
  const editAction = menuActions.find((action) => action.id === 'view-details')
  const showEdit = props.showMenuActions && editAction !== undefined
  const kebabActions = showEdit ? menuActions.filter((action) => action.id !== 'view-details') : menuActions
  const showMenu = props.showMenuActions && kebabActions.length > 0
  const showExpand = props.expandable === true

  if (!showEdit && !showExpand && !showMenu) {
    return null
  }

  return (
    <Flex alignItems={{ default: 'alignItemsCenter' }} className={`nodrag nopan ${actionsStyles.actionsRow}`}>
      {showExpand ? (
        <FlexItem>
          <SynStepExpandToggle stepLabel={props.stepTitle} />
        </FlexItem>
      ) : null}
      {showEdit && editAction ? (
        <FlexItem>
          <SynStepEditButton stepTitle={props.stepTitle} onClick={editAction.onClick} />
        </FlexItem>
      ) : null}
      {showMenu ? (
        <FlexItem>
          <SynStepMenu menuActions={kebabActions} className={props.menuClassName} popperProps={props.menuPopperProps} />
        </FlexItem>
      ) : null}
    </Flex>
  )
}
