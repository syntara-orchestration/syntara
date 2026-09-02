import { Button, Dropdown, DropdownItem, DropdownList, Icon, MenuToggle, Tooltip } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { RhUiCaretLeftIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { useCallback, useMemo, useState, type Ref } from 'react'

import { IconLabel } from '../../../components/IconLabel'
import { renderNodeIcon } from '../../workflows/canvas/nodes/renderNodeIcon'

import type { UpstreamNodeInfo } from './hooks/useUpstreamNodes'
import styles from './NodePanelNavigationArrow.module.css'
import { getUpstreamNodeDisplayName } from './utils/getUpstreamNodeDisplayName'

type NavigationDirection = 'previous' | 'next'

type NodePanelNavigationArrowProps = {
  direction: NavigationDirection
  nodes: UpstreamNodeInfo[]
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

function getNavigateAriaLabel(direction: NavigationDirection, nodeName: string): string {
  return direction === 'previous' ? `Go to previous step: ${nodeName}` : `Go to next step: ${nodeName}`
}

function NavTargetLabel({ node }: Readonly<{ node: UpstreamNodeInfo }>) {
  const name = getUpstreamNodeDisplayName(node)
  const icon = renderNodeIcon(node.icon, node.iconId, 'legend')

  return <IconLabel icon={icon ? <span aria-hidden="true">{icon}</span> : undefined}>{name}</IconLabel>
}

type SingleTargetArrowProps = {
  direction: NavigationDirection
  node: UpstreamNodeInfo
  onNavigate: (nodeId: string) => void
}

function SingleTargetArrow({ direction, node, onNavigate }: Readonly<SingleTargetArrowProps>) {
  const nodeName = getUpstreamNodeDisplayName(node)

  return (
    <Tooltip content={nodeName}>
      <Button
        variant="plain"
        type="button"
        className={getArrowClassName(direction)}
        icon={getArrowIcon(direction)}
        aria-label={getNavigateAriaLabel(direction, nodeName)}
        onClick={() => onNavigate(node.id)}
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
  nodes: UpstreamNodeInfo[]
  onNavigate: (nodeId: string) => void
}

function MultiTargetArrow({ direction, nodes, onNavigate }: Readonly<MultiTargetArrowProps>) {
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
          {nodes.map((node) => (
            <DropdownItem key={node.id} onClick={() => handleSelect(node.id)}>
              <NavTargetLabel node={node} />
            </DropdownItem>
          ))}
        </DropdownList>
      </Dropdown>
    </Tooltip>
  )
}

export function NodePanelNavigationArrow({ direction, nodes, onNavigate }: Readonly<NodePanelNavigationArrowProps>) {
  if (nodes.length === 0) {
    return null
  }

  if (nodes.length === 1) {
    const node = nodes[0]
    if (node === undefined) {
      return null
    }
    return <SingleTargetArrow direction={direction} node={node} onNavigate={onNavigate} />
  }

  return <MultiTargetArrow direction={direction} nodes={nodes} onNavigate={onNavigate} />
}
