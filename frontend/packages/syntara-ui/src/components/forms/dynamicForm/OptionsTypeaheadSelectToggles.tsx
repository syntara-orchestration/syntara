import {
  Button,
  Label,
  LabelGroup,
  MenuToggle,
  type MenuToggleElement,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'

import type { OptionScalarValue } from './synDynamicFormSelectHelpers'

export type SelectedChip = Readonly<{
  key: string
  label: string
  value: OptionScalarValue
}>

type SingleTypeaheadToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  fieldId: string
  ariaLabel: string
  isOpen: boolean
  isDisabled: boolean
  filterValue: string
  displayValue: string
  placeholder: string
  onToggle: () => void
  onFilterChange: (value: string) => void
  onClearSelection: () => void
  hasSelection: boolean
}>

export function SingleTypeaheadToggle({
  toggleRef,
  fieldId,
  ariaLabel,
  isOpen,
  isDisabled,
  filterValue,
  displayValue,
  placeholder,
  onToggle,
  onFilterChange,
  onClearSelection,
  hasSelection,
}: SingleTypeaheadToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      id={fieldId}
      variant="typeahead"
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      aria-label={ariaLabel}
    >
      <TextInputGroup isPlain isDisabled={isDisabled}>
        <TextInputGroupMain
          inputId={fieldId}
          value={isOpen ? filterValue : displayValue}
          onChange={(_event, val) => {
            onFilterChange(val)
          }}
          onClick={() => {
            if (!isOpen) onToggle()
          }}
          placeholder={placeholder}
          autoComplete="off"
          aria-label={ariaLabel}
        />
        {hasSelection && !isDisabled && (
          <TextInputGroupUtilities>
            <Button
              variant="plain"
              onClick={(event) => {
                event.stopPropagation()
                onClearSelection()
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

type MultiTypeaheadToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  fieldId: string
  ariaLabel: string
  isOpen: boolean
  isDisabled: boolean
  filterValue: string
  placeholder: string
  selectedChips: readonly SelectedChip[]
  onToggle: () => void
  onFilterChange: (value: string) => void
  onRemoveSelection: (value: OptionScalarValue) => void
  onClearAll: () => void
  inputRef: React.RefObject<HTMLInputElement | null>
}>

export function MultiTypeaheadToggle({
  toggleRef,
  fieldId,
  ariaLabel,
  isOpen,
  isDisabled,
  filterValue,
  placeholder,
  selectedChips,
  onToggle,
  onFilterChange,
  onRemoveSelection,
  onClearAll,
  inputRef,
}: MultiTypeaheadToggleProps) {
  const hasSelection = selectedChips.length > 0

  return (
    <MenuToggle
      ref={toggleRef}
      id={fieldId}
      variant="typeahead"
      onClick={onToggle}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      aria-label={ariaLabel}
    >
      <TextInputGroup isPlain isDisabled={isDisabled}>
        <TextInputGroupMain
          value={filterValue}
          onChange={(_event, val) => {
            onFilterChange(val)
          }}
          onClick={() => {
            if (!isOpen) onToggle()
          }}
          placeholder={hasSelection ? '' : placeholder}
          autoComplete="off"
          innerRef={inputRef}
          aria-label={ariaLabel}
        >
          {hasSelection && (
            <LabelGroup numLabels={3}>
              {selectedChips.map((chip) => (
                <Label
                  key={chip.key}
                  color="blue"
                  onClose={(event) => {
                    event.stopPropagation()
                    onRemoveSelection(chip.value)
                  }}
                >
                  {chip.label}
                </Label>
              ))}
            </LabelGroup>
          )}
        </TextInputGroupMain>
        {hasSelection && (
          <TextInputGroupUtilities>
            <Button
              variant="plain"
              onClick={(event) => {
                event.stopPropagation()
                onClearAll()
              }}
              aria-label="Clear all"
            >
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        )}
      </TextInputGroup>
    </MenuToggle>
  )
}

type OptionsTypeaheadMenuToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isMulti: boolean
  fieldId: string
  ariaLabel: string
  isOpen: boolean
  toggleDisabled: boolean
  filterValue: string
  displayValue: string
  placeholder: string
  selectedChips: readonly SelectedChip[]
  hasSelection: boolean
  onToggle: () => void
  onFilterChange: (value: string) => void
  onClearSingle: () => void
  onRemoveMulti: (value: OptionScalarValue) => void
  onClearMulti: () => void
  inputRef: React.RefObject<HTMLInputElement | null>
}>

export function OptionsTypeaheadMenuToggle({
  toggleRef,
  isMulti,
  fieldId,
  ariaLabel,
  isOpen,
  toggleDisabled,
  filterValue,
  displayValue,
  placeholder,
  selectedChips,
  hasSelection,
  onToggle,
  onFilterChange,
  onClearSingle,
  onRemoveMulti,
  onClearMulti,
  inputRef,
}: OptionsTypeaheadMenuToggleProps) {
  if (isMulti) {
    return (
      <MultiTypeaheadToggle
        toggleRef={toggleRef}
        fieldId={fieldId}
        ariaLabel={ariaLabel}
        isOpen={isOpen}
        isDisabled={toggleDisabled}
        filterValue={filterValue}
        placeholder={placeholder}
        selectedChips={selectedChips}
        onToggle={onToggle}
        onFilterChange={onFilterChange}
        onRemoveSelection={onRemoveMulti}
        onClearAll={onClearMulti}
        inputRef={inputRef}
      />
    )
  }

  return (
    <SingleTypeaheadToggle
      toggleRef={toggleRef}
      fieldId={fieldId}
      ariaLabel={ariaLabel}
      isOpen={isOpen}
      isDisabled={toggleDisabled}
      filterValue={filterValue}
      displayValue={displayValue}
      placeholder={placeholder}
      onToggle={onToggle}
      onFilterChange={onFilterChange}
      onClearSelection={onClearSingle}
      hasSelection={hasSelection}
    />
  )
}
