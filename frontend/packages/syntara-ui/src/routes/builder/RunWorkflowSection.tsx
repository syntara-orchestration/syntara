import { Button, Dropdown, Icon, MenuToggle, type MenuToggleElement } from '@patternfly/react-core'
import { RhUiPlayIcon } from '@patternfly/react-icons'
import { useCallback, useState, type Dispatch, type ReactElement, type Ref } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { RunWorkflowTriggerDropdownList } from '../workflows/RunWorkflowTriggerDropdownList'

import type { BuilderAction } from './builderReducer'
import styles from './RunWorkflowSection.module.css'
import type { BuilderPermissions } from './useBuilderPermissions'
import { workflowVerificationBlockedTooltip } from './workflowVerificationBlockedTooltip'

type RunMenuToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isExpanded: boolean
  isRunDisabled: boolean
  onClick: (() => void) | undefined
  keepFocusableWhenDisabled?: boolean
}>

function RunMenuToggle({
  toggleRef,
  isExpanded,
  isRunDisabled,
  onClick,
  keepFocusableWhenDisabled = false,
}: RunMenuToggleProps) {
  const useNativeDisabled = isRunDisabled && !keepFocusableWhenDisabled
  const showDisabledVisual = isRunDisabled && keepFocusableWhenDisabled
  return (
    <MenuToggle
      ref={toggleRef}
      variant="plainText"
      onClick={onClick}
      isExpanded={isExpanded}
      isDisabled={useNativeDisabled}
      aria-disabled={keepFocusableWhenDisabled && isRunDisabled ? true : undefined}
      aria-label="Run workflow"
      className={showDisabledVisual ? styles.runActionDisabled : undefined}
      icon={
        <Icon isInline>
          <RhUiPlayIcon />
        </Icon>
      }
    >
      Run
    </MenuToggle>
  )
}

export type RunWorkflowSectionProps = Readonly<{
  triggers?: { id: string; name?: string }[]
  isSaved: boolean
  validationErrorCount: number
  /** Blocking errors from the builder banner when store count is stale. */
  bannerBlockingValidationErrorCount?: number
  dispatch: Dispatch<BuilderAction>
  builderPermissions: BuilderPermissions
  isNodeEditorOpen?: boolean
}>

const NO_TRIGGERS_TOOLTIP = 'At least one trigger step needs to be placed on the canvas for this workflow to run'
const SAVE_FIRST_TOOLTIP = 'Save workflow before running'
const NODE_EDITOR_TOOLTIP = 'Finish editing the current step before running'

function wrapRunControlWithDisabledTooltip(
  isRunDisabled: boolean,
  tooltipContent: string,
  control: ReactElement
): ReactElement {
  if (!isRunDisabled || !tooltipContent) {
    return control
  }

  return (
    <DisabledWithTooltip isDisabled content={tooltipContent} position="bottom">
      {control}
    </DisabledWithTooltip>
  )
}

/** MenuToggle uses native disabled; use aria-disabled when the tooltip must stay keyboard reachable. */
function wrapMenuToggleWithTooltip(isRunDisabled: boolean, tooltipContent: string, toggle: ReactElement): ReactElement {
  if (!isRunDisabled || !tooltipContent) {
    return toggle
  }

  return (
    <DisabledWithTooltip isDisabled content={tooltipContent} position="bottom">
      {toggle}
    </DisabledWithTooltip>
  )
}

export function RunWorkflowSection({
  triggers,
  isSaved,
  validationErrorCount,
  bannerBlockingValidationErrorCount = 0,
  dispatch,
  builderPermissions,
  isNodeEditorOpen,
}: RunWorkflowSectionProps) {
  const [isRunDropdownOpen, setIsRunDropdownOpen] = useState(false)
  const hasTriggers = (triggers?.length ?? 0) > 0
  const hasMultipleTriggers = (triggers?.length ?? 0) > 1
  const effectiveValidationErrorCount = Math.max(validationErrorCount, bannerBlockingValidationErrorCount)
  const hasValidationErrors = effectiveValidationErrorCount > 0

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
    runTooltipContent = workflowVerificationBlockedTooltip('running', effectiveValidationErrorCount)
  }

  const renderRunToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => {
      const toggle = (
        <RunMenuToggle
          toggleRef={toggleRef}
          isExpanded={isRunDropdownOpen}
          isRunDisabled={isRunDisabled}
          keepFocusableWhenDisabled={isRunDisabled && Boolean(runTooltipContent)}
          onClick={!isRunDisabled ? () => setIsRunDropdownOpen((prev) => !prev) : undefined}
        />
      )
      return wrapMenuToggleWithTooltip(isRunDisabled, runTooltipContent, toggle)
    },
    [isRunDropdownOpen, isRunDisabled, runTooltipContent]
  )

  if (hasMultipleTriggers) {
    return (
      <Dropdown
        isOpen={isRunDropdownOpen}
        onOpenChange={setIsRunDropdownOpen}
        toggle={renderRunToggle}
        popperProps={{ position: 'left' }}
      >
        <RunWorkflowTriggerDropdownList
          options={(triggers ?? []).map((trigger, index) => ({
            id: trigger.id,
            label: trigger.name ?? `Trigger ${index + 1}`,
          }))}
          onSelect={(option) => {
            const index = triggers?.findIndex((trigger) => trigger.id === option.id) ?? -1
            if (index < 0) return
            dispatch({ type: 'SET_SELECTED_TRIGGER', payload: index })
            dispatch({ type: 'SET_CONFIRM_DIALOG', payload: true })
            setIsRunDropdownOpen(false)
          }}
        />
      </Dropdown>
    )
  }

  const runButton = (
    <Button
      variant="plain"
      isAriaDisabled={isRunDisabled}
      className={isRunDisabled ? styles.runActionDisabled : undefined}
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
  )

  return wrapRunControlWithDisabledTooltip(isRunDisabled, runTooltipContent, runButton)
}
