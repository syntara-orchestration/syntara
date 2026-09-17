import { Badge, BreadcrumbItem, Dropdown, DropdownItem, DropdownList, MenuToggle } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import type { MouseEvent, Ref } from 'react'
import { useMemo, useState } from 'react'

import type { AppBreadcrumbItem } from '../../app/breadcrumbs/appBreadcrumbItem'
import { detachPromise } from '../../utils/detachPromise'

type BreadcrumbDropdownToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement | null>
  isOpen: boolean
  middleCount: number
  /** Opens/closes the dropdown. PF6 Dropdown does not wire this — the toggle must call it. */
  onClick: () => void
}>

function BreadcrumbDropdownToggle(props: BreadcrumbDropdownToggleProps) {
  const { toggleRef, isOpen, middleCount, onClick } = props
  return (
    <MenuToggle
      ref={toggleRef}
      variant="plainText"
      isExpanded={isOpen}
      aria-label={`Earlier pages, ${middleCount} levels`}
      onClick={onClick}
    >
      <Badge>{middleCount}</Badge>
    </MenuToggle>
  )
}

/** Render function for the PF Dropdown `toggle` prop. Kept at module scope to satisfy Sonar S6478 (no nested components). */
function renderBreadcrumbDropdownToggle(
  toggleRef: Ref<MenuToggleElement | null>,
  isOpen: boolean,
  middleCount: number,
  onClick: () => void
) {
  return <BreadcrumbDropdownToggle toggleRef={toggleRef} isOpen={isOpen} middleCount={middleCount} onClick={onClick} />
}

export type SynPageBreadcrumbsCollapsedMiddleProps = Readonly<{
  middleItems: readonly AppBreadcrumbItem[]
}>

export function SynPageBreadcrumbsCollapsedMiddle(props: SynPageBreadcrumbsCollapsedMiddleProps) {
  const { middleItems } = props
  const [isOpen, setIsOpen] = useState(false)
  const navigate = useNavigate()

  const middleCount = middleItems.length

  const renderToggle = useMemo(
    () => (toggleRef: Ref<MenuToggleElement | null>) =>
      renderBreadcrumbDropdownToggle(toggleRef, isOpen, middleCount, () => setIsOpen((open) => !open)),
    [isOpen, middleCount]
  )

  return (
    <BreadcrumbItem isDropdown>
      <Dropdown isOpen={isOpen} onOpenChange={setIsOpen} toggle={renderToggle}>
        <DropdownList>
          {middleItems.map((item) => (
            <DropdownItem
              key={item.href ?? item.label}
              to={item.href}
              onClick={(e: MouseEvent) => {
                if (item.href && !(e.metaKey || e.altKey || e.ctrlKey || e.shiftKey || e.button !== 0)) {
                  e.preventDefault()
                  detachPromise(navigate({ to: item.href }))
                }
                setIsOpen(false)
              }}
            >
              {item.label}
            </DropdownItem>
          ))}
        </DropdownList>
      </Dropdown>
    </BreadcrumbItem>
  )
}
