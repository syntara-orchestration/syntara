import { SelectList } from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import type { ReactElement, Ref } from 'react'
import { useCallback, useMemo, useState } from 'react'
import type { ControllerFieldState, ControllerRenderProps, FieldPath, FieldValues } from 'react-hook-form'

import { SynSelect } from '../SynSelect'

import { SynSelectFieldToggle, type SynSelectFieldToggleState } from './synSelectFieldToggle'
import type { SynSelectFieldOption } from './synSelectFieldTypes'

function renderSynSelectFieldToggle(toggleRef: Ref<MenuToggleElement>, state: SynSelectFieldToggleState) {
  return <SynSelectFieldToggle toggleRef={toggleRef} {...state} />
}

type SynSelectFieldControlShellProps<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>> = {
  field: ControllerRenderProps<TFieldValues, TName>
  fieldState: ControllerFieldState
  resolvedFieldId: string
  label: string
  options: SynSelectFieldOption[]
  displayLabel: string
  selected: string | string[]
  onSelect: (_event: React.MouseEvent | undefined, value: string | number | undefined) => void
  isDisabled?: boolean
  closeOnSelect?: boolean
  shouldFocusToggleOnSelect?: boolean
  renderOption: (option: SynSelectFieldOption, isSelected: boolean) => ReactElement
}

export function SynSelectFieldControlShell<TFieldValues extends FieldValues, TName extends FieldPath<TFieldValues>>({
  field,
  fieldState,
  resolvedFieldId,
  label,
  options,
  displayLabel,
  selected,
  onSelect,
  isDisabled,
  closeOnSelect = false,
  shouldFocusToggleOnSelect,
  renderOption,
}: Readonly<SynSelectFieldControlShellProps<TFieldValues, TName>>) {
  const [isOpen, setIsOpen] = useState(false)
  const hasError = Boolean(fieldState.error)

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
      displayLabel,
      isOpen,
      onToggle: handleToggle,
      onBlur: field.onBlur,
      isDisabled,
      hasError,
    }),
    [displayLabel, field.onBlur, handleToggle, hasError, isDisabled, isOpen, resolvedFieldId]
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
