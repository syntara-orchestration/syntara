import {
  Button,
  MenuToggle,
  type MenuToggleElement,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import React, { useRef } from 'react'

export type TypeaheadMenuToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  displayText: string
  ariaLabel: string
  fieldId: string
  isOpen: boolean
  isDisabled: boolean
  isPending: boolean
  hasSelection: boolean
  filterText: string
  placeholder: string
  loadingPlaceholder?: string
  isInvalid?: boolean
  describedBy?: string
  onFilterChange: (val: string) => void
  onClear: () => void
  onToggle: () => void
}>

export function TypeaheadMenuToggle({
  toggleRef,
  displayText,
  ariaLabel,
  fieldId,
  isOpen,
  isDisabled,
  isPending,
  hasSelection,
  filterText,
  placeholder,
  loadingPlaceholder = 'Loading...',
  isInvalid,
  describedBy,
  onFilterChange,
  onClear,
  onToggle,
}: TypeaheadMenuToggleProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const showClearFilter = isOpen && filterText
  const showClearSelection = !isOpen && hasSelection && !isDisabled && !isPending

  return (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      tabIndex={-1}
      isExpanded={isOpen}
      isDisabled={isDisabled || isPending}
      isFullWidth
      aria-label={ariaLabel}
      aria-invalid={isInvalid || undefined}
      aria-describedby={describedBy}
      status={isInvalid ? 'danger' : undefined}
      onClick={onToggle}
      onFocus={(event) => {
        if (event.target === event.currentTarget) inputRef.current?.focus()
      }}
    >
      <TextInputGroup isPlain isDisabled={isDisabled || isPending}>
        <TextInputGroupMain
          value={isOpen ? filterText : displayText}
          placeholder={isPending ? loadingPlaceholder : placeholder}
          onClick={(e) => {
            e.stopPropagation()
            if (!isOpen) onToggle()
          }}
          onChange={(_event, val) => onFilterChange(val)}
          inputId={`${fieldId}-filter`}
          innerRef={inputRef}
          inputProps={{
            autoComplete: 'off',
            'aria-invalid': isInvalid || undefined,
            'aria-describedby': describedBy,
            onKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => {
              if (event.key === 'Enter' || event.key === 'ArrowDown') {
                event.preventDefault()
                if (!isOpen) onToggle()
              }
            },
          }}
          aria-label={ariaLabel}
        />
        {showClearFilter && (
          <TextInputGroupUtilities>
            <Button
              variant="plain"
              onClick={(event) => {
                event.stopPropagation()
                onFilterChange('')
                inputRef.current?.focus()
              }}
              aria-label="Clear filter"
            >
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        )}
        {showClearSelection && (
          <TextInputGroupUtilities>
            <Button
              variant="plain"
              onClick={(e) => {
                e.stopPropagation()
                onClear()
              }}
              aria-label="Clear selection"
            >
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        )}
      </TextInputGroup>
    </MenuToggle>
  )
}
