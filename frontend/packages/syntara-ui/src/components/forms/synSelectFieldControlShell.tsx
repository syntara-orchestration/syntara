import { SelectList } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import type { ReactElement, Ref } from 'react'
import { useCallback, useMemo, useRef, useState } from 'react'
import type { ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'

import { SynSelect } from '../SynSelect'

import { SynSelectFieldToggle, type SynSelectFieldToggleState } from './synSelectFieldToggle'
import type { SynSelectFieldOption } from './synSelectFieldTypes'

function renderSynSelectFieldToggle(toggleRef: Ref<MenuToggleElement>, state: SynSelectFieldToggleState) {
  return <SynSelectFieldToggle toggleRef={toggleRef} {...state} />
}

/** PatternFly's default arrow handler always lands on the first or last item. Move relative to the current option instead. */
function focusSelectOptionFromToggle(menu: HTMLElement, key: 'ArrowDown' | 'ArrowUp') {
  const options = Array.from(menu.querySelectorAll<HTMLElement>('[role="option"]:not([aria-disabled="true"])'))
  if (options.length > 0) {
    const selectedIndex = options.findIndex((option) => option.getAttribute('aria-selected') === 'true')
    const direction = key === 'ArrowDown' ? 1 : -1
    const unselectedIndex = key === 'ArrowDown' ? 0 : options.length - 1
    const nextIndex =
      selectedIndex < 0 ? unselectedIndex : (selectedIndex + direction + options.length) % options.length
    options[nextIndex]?.focus()
    return
  }
  const items = Array.from(menu.querySelectorAll<HTMLElement>('li button:not(:disabled), li input:not(:disabled)'))
  const target = key === 'ArrowDown' ? items[0] : items[items.length - 1]
  target?.focus()
}

type SynSelectFieldControlShellProps<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  field: ControllerRenderProps<TFieldValues, TName>
  fieldState: ControllerFieldState
  resolvedFieldId: string
  label: string
  ariaLabel?: string
  options: SynSelectFieldOption[]
  displayLabel: string
  selected: string | string[]
  onSelect: (_event: React.MouseEvent | undefined, value: string | number | undefined) => void
  isDisabled?: boolean
  describedBy?: string
  closeOnSelect?: boolean
  shouldFocusToggleOnSelect?: boolean
  renderOption: (option: SynSelectFieldOption, isSelected: boolean) => ReactElement
}

export function SynSelectFieldControlShell<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>>({
  field,
  fieldState,
  resolvedFieldId,
  label,
  ariaLabel,
  options,
  displayLabel,
  selected,
  onSelect,
  isDisabled,
  describedBy,
  closeOnSelect = false,
  shouldFocusToggleOnSelect,
  renderOption,
}: Readonly<SynSelectFieldControlShellProps<TFieldValues, TName>>) {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const hasError = Boolean(fieldState.error)
  const handleToggleKeydown = useCallback(
    (event: KeyboardEvent) => {
      if (!isOpen || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') || !menuRef.current) return
      event.preventDefault()
      focusSelectOptionFromToggle(menuRef.current, event.key)
    },
    [isOpen]
  )

  const handleToggle = useCallback(() => {
    setIsOpen((open) => !open)
  }, [])

  const handleSelect = useCallback(
    (event: React.MouseEvent | undefined, value: string | number | undefined) => {
      onSelect(event, value)
      if (closeOnSelect) {
        setIsOpen(false)
      }
    },
    [closeOnSelect, onSelect]
  )

  const toggleState = useMemo<SynSelectFieldToggleState>(
    () => ({
      fieldId: resolvedFieldId,
      ariaLabel,
      displayLabel,
      isOpen,
      onToggle: handleToggle,
      onBlur: field.onBlur,
      isDisabled,
      hasError,
      describedBy,
    }),
    [ariaLabel, describedBy, displayLabel, field.onBlur, handleToggle, hasError, isDisabled, isOpen, resolvedFieldId]
  )

  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => renderSynSelectFieldToggle(toggleRef, toggleState),
    [toggleState]
  )

  return (
    <SynSelect
      isOpen={isOpen}
      selected={selected}
      onSelect={handleSelect}
      onOpenChange={setIsOpen}
      onToggleKeydown={handleToggleKeydown}
      menuRef={menuRef}
      toggle={renderToggle}
      shouldFocusToggleOnSelect={shouldFocusToggleOnSelect}
    >
      <SelectList aria-label={`${label} options`}>
        {options.map((option) =>
          renderOption(option, Array.isArray(selected) ? selected.includes(option.value) : option.value === selected)
        )}
      </SelectList>
    </SynSelect>
  )
}
