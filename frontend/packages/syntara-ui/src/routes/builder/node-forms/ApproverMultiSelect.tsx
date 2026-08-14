/**
 * Generic multi-select component for approvers (users or groups) with typeahead filtering
 */

import {
  Button,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Label,
  LabelGroup,
  MenuToggle,
  SelectList,
  SelectOption,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon, RhUiErrorIcon } from '@patternfly/react-icons'
import { useCallback, useMemo, useRef, useState } from 'react'

import { NxSelect } from '../../../components/NxSelect'

// Generic item type for multi-select
export type SelectableItem = {
  id: string
  [key: string]: unknown
}

type ApproverMultiSelectProps<T extends SelectableItem> = Readonly<{
  value: readonly string[]
  onChange: (value: string[]) => void
  items: readonly T[]
  isLoading: boolean
  validationError?: Readonly<{ message?: string }>
  getItemId: (item: T) => string
  getItemValue: (item: T) => string
  getItemLabel: (item: T) => string
  placeholderText: string
  emptyText: string
  loadingText: string
  helperText: string
  allowCustomValue?: boolean
}>

export function ApproverMultiSelect<T extends SelectableItem>({
  value,
  onChange,
  items,
  isLoading,
  validationError,
  getItemId,
  getItemValue,
  getItemLabel,
  placeholderText,
  emptyText,
  loadingText,
  helperText,
  allowCustomValue,
}: ApproverMultiSelectProps<T>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const selectedValues = useMemo(() => value ?? [], [value])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selection: string | number | undefined) => {
      if (!selection) return
      const itemValue = String(selection)

      const newValues = selectedValues.includes(itemValue)
        ? selectedValues.filter((v) => v !== itemValue)
        : [...selectedValues, itemValue]

      onChange(newValues)
      setFilterValue('')
    },
    [selectedValues, onChange]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (!allowCustomValue) return
      if (e.key === 'Enter' && filterValue.trim()) {
        e.preventDefault()
        const customValue = filterValue.trim()
        if (!selectedValues.includes(customValue)) {
          onChange([...selectedValues, customValue])
          setFilterValue('')
        }
      }
    },
    [allowCustomValue, filterValue, selectedValues, onChange]
  )

  const clearAll = useCallback(() => {
    onChange([])
    setFilterValue('')
    inputRef.current?.focus()
  }, [onChange])

  // Filter items based on search input
  const filteredItems = useMemo(() => {
    if (!filterValue) return items
    const lowerFilter = filterValue.toLowerCase()
    return items.filter((item) => getItemLabel(item).toLowerCase().includes(lowerFilter))
  }, [items, filterValue, getItemLabel])

  // Reset filter when menu closes
  const handleOpenChange = useCallback((isOpen: boolean) => {
    setIsOpen(isOpen)
    if (!isOpen) {
      setFilterValue('')
    }
  }, [])

  const selectedChips = useMemo(
    () =>
      selectedValues.map((val) => {
        const item = items.find((i) => getItemValue(i) === val)
        if (item) {
          return { key: val, label: getItemLabel(item), value: getItemValue(item) }
        }
        return { key: val, label: val, value: val }
      }),
    [selectedValues, items, getItemValue, getItemLabel]
  )

  const handleRemoveSelection = useCallback(
    (valueToRemove: string) => {
      onChange(selectedValues.filter((v) => v !== valueToRemove))
    },
    [selectedValues, onChange]
  )

  const toggle = useCallback(
    (toggleRef: React.Ref<HTMLButtonElement>) => (
      <MenuToggle
        ref={toggleRef}
        variant="typeahead"
        onClick={() => setIsOpen((prev) => !prev)}
        isExpanded={isOpen}
        isFullWidth
        isDisabled={isLoading}
        status={validationError ? 'danger' : undefined}
      >
        <TextInputGroup isPlain isDisabled={isLoading}>
          <TextInputGroupMain
            value={filterValue}
            onChange={(_event, val) => {
              setFilterValue(val)
              if (!isOpen) setIsOpen(true)
            }}
            onClick={() => {
              if (!isOpen) setIsOpen(true)
            }}
            onKeyDown={handleKeyDown}
            placeholder={selectedValues.length === 0 ? placeholderText : ''}
            autoComplete="off"
            innerRef={inputRef}
          >
            {selectedChips.length > 0 && (
              <LabelGroup numLabels={3}>
                {selectedChips.map((chip) => (
                  <Label
                    key={chip.key}
                    color="blue"
                    onClose={(e) => {
                      e.stopPropagation()
                      handleRemoveSelection(chip.value)
                    }}
                  >
                    {chip.label}
                  </Label>
                ))}
              </LabelGroup>
            )}
          </TextInputGroupMain>
          {selectedValues.length > 0 && (
            <TextInputGroupUtilities>
              <Button
                variant="plain"
                onClick={(e) => {
                  e.stopPropagation()
                  clearAll()
                }}
                aria-label="Clear all"
              >
                <RhUiCloseIcon />
              </Button>
            </TextInputGroupUtilities>
          )}
        </TextInputGroup>
      </MenuToggle>
    ),
    [
      isOpen,
      isLoading,
      selectedValues.length,
      placeholderText,
      filterValue,
      validationError,
      clearAll,
      handleKeyDown,
      selectedChips,
      handleRemoveSelection,
    ]
  )

  return (
    <>
      <NxSelect
        isOpen={isOpen}
        selected={selectedValues}
        onSelect={handleSelect}
        onOpenChange={handleOpenChange}
        toggle={toggle}
        shouldFocusToggleOnSelect
      >
        <SelectList>
          {filteredItems.map((item) => (
            <SelectOption
              key={getItemId(item)}
              value={getItemValue(item)}
              hasCheckbox
              isSelected={selectedValues.includes(getItemValue(item))}
            >
              {getItemLabel(item)}
            </SelectOption>
          ))}
          {filteredItems.length === 0 && !isLoading && <SelectOption isDisabled>{emptyText}</SelectOption>}
          {isLoading && <SelectOption isDisabled>{loadingText}</SelectOption>}
        </SelectList>
      </NxSelect>

      {validationError && (
        <FormHelperText>
          <HelperText>
            <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
              {validationError.message}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      )}
      <FormHelperText>
        <HelperText>
          <HelperTextItem>{helperText}</HelperTextItem>
        </HelperText>
      </FormHelperText>
    </>
  )
}
