import {
  Button,
  Dropdown,
  DropdownItem,
  DropdownList,
  Icon,
  MenuToggle,
  type MenuToggleElement,
} from '@patternfly/react-core'
import { RhUiPlayIcon } from '@patternfly/react-icons'
import { useCallback, useState, type Dispatch, type Ref } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'

import type { BuilderAction } from './builderReducer'
import type { BuilderPermissions } from './useBuilderPermissions'

type RunMenuToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isExpanded: boolean
  isDisabled: boolean
  onClick: (() => void) | undefined
}>

function RunMenuToggle({ toggleRef, isExpanded, isDisabled, onClick }: RunMenuToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      variant="plain"
      onClick={onClick}
      isExpanded={isExpanded}
      isDisabled={isDisabled}
      aria-label="Run workflow"
    >
      <Icon isInline>
        <RhUiPlayIcon />
      </Icon>{' '}
      Run
    </MenuToggle>
  )
}

export type RunWorkflowSectionProps = Readonly<{
  triggers?: { id: string; name?: string }[]
  isSaved: boolean
  validationErrorCount: number
  dispatch: Dispatch<BuilderAction>
  builderPermissions: BuilderPermissions
  isNodeEditorOpen?: boolean
}>

const NO_TRIGGERS_TOOLTIP = 'At least one trigger step needs to be placed on the canvas for this workflow to run'
const SAVE_FIRST_TOOLTIP = 'Save workflow before running'
const NODE_EDITOR_TOOLTIP = 'Finish editing the current step before running'

export function RunWorkflowSection({
  triggers,
  isSaved,
  validationErrorCount,
  dispatch,
  builderPermissions,
  isNodeEditorOpen,
}: RunWorkflowSectionProps) {
  const [isRunDropdownOpen, setIsRunDropdownOpen] = useState(false)
  const hasTriggers = (triggers?.length ?? 0) > 0
  const hasMultipleTriggers = (triggers?.length ?? 0) > 1
  const hasValidationErrors = validationErrorCount > 0

  const isRunDisabled =
    !builderPermissions.canRun || !!isNodeEditorOpen || !hasTriggers || !isSaved || hasValidationErrors

  let runTooltipContent = ''
  if (!builderPermissions.canRun) {
    runTooltipContent = builderPermissions.tooltips.run
  } else if (isNodeEditorOpen) {
    runTooltipContent = NODE_EDITOR_TOOLTIP
  } else if (!isSaved) {
    runTooltipContent = SAVE_FIRST_TOOLTIP
  } else if (!hasTriggers) {
    runTooltipContent = NO_TRIGGERS_TOOLTIP
  } else if (hasValidationErrors) {
    const suffix = validationErrorCount === 1 ? '' : 's'
    runTooltipContent = `Resolve validation issue${suffix} before running — ${validationErrorCount} found`
  }

  const renderRunToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <RunMenuToggle
        toggleRef={toggleRef}
        isExpanded={isRunDropdownOpen}
        isDisabled={isRunDisabled}
        onClick={!isRunDisabled ? () => setIsRunDropdownOpen((prev) => !prev) : undefined}
      />
    ),
    [isRunDropdownOpen, isRunDisabled]
  )

  if (hasMultipleTriggers) {
    return (
      <DisabledWithTooltip isDisabled={isRunDisabled} content={runTooltipContent} position="bottom">
        <Dropdown
          isOpen={isRunDropdownOpen}
          onOpenChange={setIsRunDropdownOpen}
          toggle={renderRunToggle}
          popperProps={{ position: 'left' }}
        >
          <DropdownList>
            {triggers?.map((trigger, index) => (
              <DropdownItem
                key={trigger.id}
                onClick={() => {
                  dispatch({ type: 'SET_SELECTED_TRIGGER', payload: index })
                  dispatch({ type: 'SET_CONFIRM_DIALOG', payload: true })
                  setIsRunDropdownOpen(false)
                }}
              >
                {trigger.name ?? `Trigger ${index + 1}`}
              </DropdownItem>
            ))}
          </DropdownList>
        </Dropdown>
      </DisabledWithTooltip>
    )
  }

  return (
    <DisabledWithTooltip isDisabled={isRunDisabled} content={runTooltipContent} position="bottom">
      <Button
        variant="plain"
        isAriaDisabled={isRunDisabled}
        onClick={!isRunDisabled ? () => dispatch({ type: 'SET_CONFIRM_DIALOG', payload: true }) : undefined}
        icon={
          <Icon isInline>
            <RhUiPlayIcon />
          </Icon>
        }
        iconPosition="start"
      >
        Run
      </Button>
    </DisabledWithTooltip>
  )
}
