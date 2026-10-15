import { Button, Dropdown, DropdownItem, DropdownList, Icon, MenuToggle, Tooltip } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { RhUiCaretLeftIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { useCallback, useMemo, useState, type Ref } from 'react'

import { IconLabel } from '../../../components/IconLabel'
import { renderStepIcon } from '../../workflows/canvas/nodes/renderStepIcon'

import type { UpstreamStepInfo } from './hooks/useUpstreamSteps'
import styles from './StepPanelNavigationArrow.module.css'
import { getUpstreamStepDisplayName } from './utils/getUpstreamStepDisplayName'

type NavigationDirection = 'previous' | 'next'

type StepPanelNavigationArrowProps = {
  direction: NavigationDirection
  steps: UpstreamStepInfo[]
  onNavigate: (nodeId: string) => void
}

function getMultiTargetTooltip(direction: NavigationDirection): string {
  return direction === 'previous' ? 'Previous step' : 'Next step'
}

function getArrowIcon(direction: NavigationDirection) {
  const CaretIcon = direction === 'previous' ? RhUiCaretLeftIcon : RhUiCaretRightIcon
  return (
    <Icon isInline>
      <CaretIcon />
    </Icon>
  )
}

function getArrowClassName(direction: NavigationDirection): string {
  return direction === 'previous' ? styles.arrowTabPrevious : styles.arrowTabNext
}

function getNavigateAriaLabel(direction: NavigationDirection, stepName: string): string {
  return direction === 'previous' ? `Go to previous step: ${stepName}` : `Go to next step: ${stepName}`
}

function NavTargetLabel({ step }: Readonly<{ step: UpstreamStepInfo }>) {
  const name = getUpstreamStepDisplayName(step)
  const icon = renderStepIcon(step.icon, step.iconId, 'legend')

  return <IconLabel icon={icon ? <span aria-hidden="true">{icon}</span> : undefined}>{name}</IconLabel>
}

type SingleTargetArrowProps = {
  direction: NavigationDirection
  step: UpstreamStepInfo
  onNavigate: (nodeId: string) => void
}

function SingleTargetArrow({ direction, step, onNavigate }: Readonly<SingleTargetArrowProps>) {
  const stepName = getUpstreamStepDisplayName(step)

  return (
    <Tooltip content={stepName}>
      <Button
        variant="plain"
        type="button"
        className={getArrowClassName(direction)}
        icon={getArrowIcon(direction)}
        aria-label={getNavigateAriaLabel(direction, stepName)}
        onClick={() => onNavigate(step.id)}
      />
    </Tooltip>
  )
}

type MultiTargetArrowToggleProps = {
  toggleRef: Ref<MenuToggleElement>
  direction: NavigationDirection
  tooltip: string
  isOpen: boolean
  onToggle: () => void
}

function MultiTargetArrowToggle({
  toggleRef,
  direction,
  tooltip,
  isOpen,
  onToggle,
}: Readonly<MultiTargetArrowToggleProps>) {
  return (
    <MenuToggle
      ref={toggleRef}
      variant="plain"
      className={getArrowClassName(direction)}
      aria-label={tooltip}
      isExpanded={isOpen}
      onClick={onToggle}
    >
      {getArrowIcon(direction)}
    </MenuToggle>
  )
}

type MultiTargetArrowToggleRenderProps = Omit<MultiTargetArrowToggleProps, 'toggleRef'>

function createMultiTargetArrowToggleRenderer(props: Readonly<MultiTargetArrowToggleRenderProps>) {
  function renderMultiTargetArrowToggle(toggleRef: Ref<MenuToggleElement>) {
    return <MultiTargetArrowToggle toggleRef={toggleRef} {...props} />
  }

  return renderMultiTargetArrowToggle
}

type MultiTargetArrowProps = {
  direction: NavigationDirection
  steps: UpstreamStepInfo[]
  onNavigate: (nodeId: string) => void
}

function MultiTargetArrow({ direction, steps, onNavigate }: Readonly<MultiTargetArrowProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const tooltip = getMultiTargetTooltip(direction)

  const handleSelect = useCallback(
    (nodeId: string) => {
      onNavigate(nodeId)
      setIsOpen(false)
    },
    [onNavigate]
  )

  const handleToggleOpen = useCallback(() => setIsOpen((prev) => !prev), [])

  const renderToggle = useMemo(
    () =>
      createMultiTargetArrowToggleRenderer({
        direction,
        tooltip,
        isOpen,
        onToggle: handleToggleOpen,
      }),
    [direction, tooltip, isOpen, handleToggleOpen]
  )

  return (
    <Tooltip content={tooltip}>
      <Dropdown
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        popperProps={{ placement: direction === 'previous' ? 'bottom-start' : 'bottom-end' }}
        toggle={renderToggle}
      >
        <DropdownList>
          {steps.map((step) => (
            <DropdownItem key={step.id} onClick={() => handleSelect(step.id)}>
              <NavTargetLabel step={step} />
            </DropdownItem>
          ))}
        </DropdownList>
      </Dropdown>
    </Tooltip>
  )
}

export function StepPanelNavigationArrow({ direction, steps, onNavigate }: Readonly<StepPanelNavigationArrowProps>) {
  if (steps.length === 0) {
    return null
  }

  if (steps.length === 1) {
    const step = steps[0]
    if (step === undefined) {
      return null
    }
    return <SingleTargetArrow direction={direction} step={step} onNavigate={onNavigate} />
  }

  return <MultiTargetArrow direction={direction} steps={steps} onNavigate={onNavigate} />
}
