import {
  Button,
  MenuToggle,
  type MenuToggleElement,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import React from 'react'

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
  onFilterChange,
  onClear,
  onToggle,
}: TypeaheadMenuToggleProps) {
  const showClearFilter = isOpen && filterText
  const showClearSelection = !isOpen && hasSelection && !isDisabled && !isPending

  return (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      isExpanded={isOpen}
      isDisabled={isDisabled || isPending}
      isFullWidth
      aria-label={ariaLabel}
      onClick={onToggle}
    >
      <TextInputGroup isPlain isDisabled={isDisabled || isPending}>
        <TextInputGroupMain
          value={isOpen ? filterText : displayText}
          placeholder={isPending ? loadingPlaceholder : placeholder}
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          onChange={(_event, val) => onFilterChange(val)}
          autoComplete="off"
          inputId={fieldId}
          aria-label={ariaLabel}
        />
        {showClearFilter && (
          <TextInputGroupUtilities>
            <Button variant="plain" onClick={() => onFilterChange('')} aria-label="Clear filter">
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
