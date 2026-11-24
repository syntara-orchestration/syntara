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
import styles from './RunWorkflowSection.module.css'
import type { BuilderPermissions } from './useBuilderPermissions'

type RunMenuToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isExpanded: boolean
  isDisabled: boolean
  tooltipContent: string
  onClick: (() => void) | undefined
}>

function RunMenuToggle({ toggleRef, isExpanded, isDisabled, tooltipContent, onClick }: RunMenuToggleProps) {
  return (
    <DisabledWithTooltip isDisabled={isDisabled} content={tooltipContent} position="bottom">
      <MenuToggle
        ref={toggleRef}
        variant="plain"
        className={styles.toggle}
        onClick={onClick}
        isExpanded={isExpanded}
        aria-disabled={isDisabled}
        aria-label="Run workflow"
      >
        <Icon isInline>
          <RhUiPlayIcon />
        </Icon>{' '}
        Run
      </MenuToggle>
    </DisabledWithTooltip>
  )
}

export type RunWorkflowSectionProps = Readonly<{
  triggers?: { id: string; name?: string }[]
  isSaved: boolean
  validationErrorCount: number
  dispatch: Dispatch<BuilderAction>
  builderPermissions: BuilderPermissions
  isStepEditorOpen?: boolean
}>

const NO_TRIGGERS_TOOLTIP = 'At least one trigger step needs to be placed on the canvas for this workflow to run'
const SAVE_FIRST_TOOLTIP = 'Save workflow before running'
const NODE_EDITOR_TOOLTIP = 'Finish editing the current step before running'

export function RunWorkflowSection({
  triggers = [],
  isSaved,
  validationErrorCount,
  dispatch,
  builderPermissions,
  isStepEditorOpen,
}: RunWorkflowSectionProps) {
  const [isRunDropdownOpen, setIsRunDropdownOpen] = useState(false)
  const firstTrigger = triggers[0]
  const hasTriggers = firstTrigger !== undefined
  const hasMultipleTriggers = triggers.length > 1
  const readOnly = !builderPermissions.canEdit
  const hasValidationErrors = !readOnly && validationErrorCount > 0
  const openRunDialog = (triggerId: string) => {
    dispatch({ type: 'OPEN_RUN_DIALOG', payload: { triggerId, readOnly } })
  }

  const isRunDisabled =
    !builderPermissions.canRun || !!isStepEditorOpen || !hasTriggers || !isSaved || hasValidationErrors

  let runTooltipContent = ''
  if (!builderPermissions.canRun) {
    runTooltipContent = builderPermissions.tooltips.run
  } else if (isStepEditorOpen) {
    runTooltipContent = NODE_EDITOR_TOOLTIP
  } else if (!isSaved) {
    runTooltipContent = SAVE_FIRST_TOOLTIP
  } else if (!hasTriggers) {
    runTooltipContent = readOnly ? 'No saved trigger is available.' : NO_TRIGGERS_TOOLTIP
  } else if (hasValidationErrors) {
    const suffix = validationErrorCount === 1 ? '' : 's'
    runTooltipContent = `Resolve validation issue${suffix} before running — ${validationErrorCount} found`
  }

  const isRunMenuOpen = !isRunDisabled && isRunDropdownOpen
  const renderRunToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <RunMenuToggle
        toggleRef={toggleRef}
        isExpanded={isRunMenuOpen}
        isDisabled={isRunDisabled}
        tooltipContent={runTooltipContent}
        onClick={!isRunDisabled ? () => setIsRunDropdownOpen((prev) => !prev) : undefined}
      />
    ),
    [isRunMenuOpen, isRunDisabled, runTooltipContent]
  )

  if (hasMultipleTriggers) {
    return (
      <Dropdown
        isOpen={isRunMenuOpen}
        onOpenChange={setIsRunDropdownOpen}
        toggle={renderRunToggle}
        popperProps={{ position: 'left' }}
      >
        <DropdownList>
          {triggers.map((trigger, index) => (
            <DropdownItem
              key={trigger.id}
              onClick={() => {
                if (isRunDisabled) return
                openRunDialog(trigger.id)
                setIsRunDropdownOpen(false)
              }}
            >
              {trigger.name ?? `Trigger ${index + 1}`}
            </DropdownItem>
          ))}
        </DropdownList>
      </Dropdown>
    )
  }

  return (
    <DisabledWithTooltip isDisabled={isRunDisabled} content={runTooltipContent} position="bottom">
      <Button
        variant="plain"
        isAriaDisabled={isRunDisabled}
        onClick={!isRunDisabled && firstTrigger ? () => openRunDialog(firstTrigger.id) : undefined}
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
