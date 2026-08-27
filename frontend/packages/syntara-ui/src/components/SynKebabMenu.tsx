import { Divider, Dropdown, DropdownItem, DropdownList, MenuToggle } from '@patternfly/react-core'
import type { MenuToggleElement, TooltipProps } from '@patternfly/react-core'
import { RhUiEllipsisVerticalFillIcon } from '@patternfly/react-icons'
import { useCallback, useEffect, useId, useRef, useState } from 'react'

export type KebabAction = {
  /** Unique identifier for this action, used as the React `key`. */
  key: string
  /** Label content rendered inside the dropdown item. Omit for separators. */
  title?: React.ReactNode
  /** Callback fired when the item is clicked (ignored when `isAriaDisabled`). */
  onClick?: () => void
  /** Render a visual divider instead of a clickable item. */
  isSeparator?: boolean
  /** Apply danger styling (red text). Automatically suppressed when `isAriaDisabled`. */
  isDanger?: boolean
  /** Fully disable the item (removes it from the tab order). */
  isDisabled?: boolean
  /** Visually disable the item while keeping it focusable for assistive technology. */
  isAriaDisabled?: boolean
  /** Tooltip shown on hover — typically used to explain why the item is disabled. */
  tooltipProps?: TooltipProps
}

type SynKebabMenuProps = Readonly<{
  actions: KebabAction[]
  /** Accessible label for the toggle button — must be unique per context (e.g. per table row). */
  'aria-label': string
}>

/** Ensures only one SynKebabMenu is open at a time across the app. */
const openMenuClosers = new Map<string, () => void>()

function KebabToggle({
  toggleRef,
  isExpanded,
  ariaLabel,
  onToggle,
}: Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isExpanded: boolean
  ariaLabel: string
  onToggle: () => void
}>) {
  return (
    <MenuToggle ref={toggleRef} variant="plain" onClick={onToggle} isExpanded={isExpanded} aria-label={ariaLabel}>
      <RhUiEllipsisVerticalFillIcon />
    </MenuToggle>
  )
}

export function SynKebabMenu({ actions, 'aria-label': ariaLabel }: SynKebabMenuProps) {
  const menuId = useId()
  const [isOpen, setIsOpen] = useState(false)
  const toggleRef = useRef<MenuToggleElement>(null)

  useEffect(() => {
    openMenuClosers.set(menuId, () => setIsOpen(false))
    return () => {
      openMenuClosers.delete(menuId)
    }
  }, [menuId])

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (nextOpen) {
        for (const [id, close] of openMenuClosers) {
          if (id !== menuId) {
            close()
          }
        }
      }
      setIsOpen(nextOpen)
    },
    [menuId]
  )

  const renderToggle = useCallback(
    (ref: React.Ref<MenuToggleElement>) => (
      <KebabToggle
        toggleRef={(node: MenuToggleElement | null) => {
          ;(toggleRef as React.MutableRefObject<MenuToggleElement | null>).current = node
          if (typeof ref === 'function') ref(node)
          else if (ref && typeof ref === 'object')
            (ref as React.MutableRefObject<MenuToggleElement | null>).current = node
        }}
        isExpanded={isOpen}
        ariaLabel={ariaLabel}
        onToggle={() => handleOpenChange(!isOpen)}
      />
    ),
    [isOpen, ariaLabel, handleOpenChange]
  )

  const handleItemClick = useCallback(
    (action: KebabAction) => {
      if (action.isAriaDisabled) return
      action.onClick?.()
      handleOpenChange(false)
      // PF Dropdown asynchronously returns focus to the toggle on close.
      // If the action opened a modal (which sets aria-hidden on #root),
      // this async focus-return triggers a browser warning. Blur the toggle
      // to prevent focus from landing inside the aria-hidden subtree.
      requestAnimationFrame(() => {
        toggleRef.current?.blur()
      })
    },
    [handleOpenChange]
  )

  return (
    <Dropdown isOpen={isOpen} onOpenChange={handleOpenChange} popperProps={{ position: 'end' }} toggle={renderToggle}>
      <DropdownList>
        {actions.map((action) => {
          if (action.isSeparator) {
            return <Divider key={action.key} />
          }
          return (
            <DropdownItem
              key={action.key}
              isDanger={action.isDanger && !action.isAriaDisabled}
              isDisabled={action.isDisabled}
              isAriaDisabled={action.isAriaDisabled}
              tooltipProps={action.tooltipProps}
              onClick={() => handleItemClick(action)}
            >
              {action.title}
            </DropdownItem>
          )
        })}
      </DropdownList>
    </Dropdown>
  )
}
