import {
  Button,
  MenuToggle,
  SelectList,
  SelectOption,
  Spinner,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { type Ref, useEffect, useRef, useState } from 'react'

import { SynSelect } from '../../../components/SynSelect'

const DEBOUNCE_MS = 300

type AAPTypeaheadSelectOption = {
  readonly value: string
  readonly label: string
  readonly description?: string
}

type AAPTypeaheadSelectProps = {
  readonly id: string
  readonly ariaLabel: string
  readonly options: readonly AAPTypeaheadSelectOption[]
  readonly selected: string
  readonly onChange: (value: string) => void
  readonly onSearchChange: (search: string) => void
  readonly placeholder?: string
  readonly isLoading?: boolean
  readonly hasError?: boolean
  /** Disables the picker: no typing, no dropdown, and no clear control. */
  readonly isDisabled?: boolean
}

export function AAPTypeaheadSelect({
  id,
  ariaLabel,
  options,
  selected,
  onChange,
  onSearchChange,
  placeholder = 'Select...',
  isLoading,
  hasError,
  isDisabled,
}: AAPTypeaheadSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const selectedLabel = options.find((o) => o.value === selected)?.label ?? selected

  // Debounce the search callback for server-side filtering
  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      onSearchChange(filterValue)
    }, DEBOUNCE_MS)
    return () => clearTimeout(debounceRef.current)
  }, [filterValue, onSearchChange])

  // Clear debounce on unmount
  useEffect(() => () => clearTimeout(debounceRef.current), [])

  const onSelect = (_event: React.MouseEvent<Element, MouseEvent> | undefined, value: string | number | undefined) => {
    onChange(String(value ?? ''))
    setFilterValue('')
    setIsOpen(false)
  }

  const clear = () => {
    onChange('')
    setFilterValue('')
    inputRef.current?.focus()
  }

  // A disabled select never shows its menu, even if it was open when the prop
  // flipped — derived here instead of syncing state in an effect.
  const isMenuOpen = isOpen && !isDisabled

  const onToggle = () => {
    if (isDisabled) return
    setIsOpen((prev) => !prev)
  }

  const onInputChange = (_e: React.FormEvent<HTMLInputElement>, val: string) => {
    if (isDisabled) return
    setFilterValue(val)
    if (!isOpen) setIsOpen(true)
  }

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      onClick={onToggle}
      isDisabled={isDisabled}
      isExpanded={isMenuOpen}
      isFullWidth
      status={hasError ? 'danger' : undefined}
    >
      <TextInputGroup isPlain isDisabled={isDisabled}>
        <TextInputGroupMain
          value={isMenuOpen ? filterValue : selectedLabel}
          onChange={onInputChange}
          onClick={() => {
            if (!isDisabled && !isOpen) setIsOpen(true)
          }}
          placeholder={placeholder}
          autoComplete="off"
          innerRef={inputRef}
        />
        <TextInputGroupUtilities>
          {isLoading && <Spinner size="sm" aria-label="Loading" />}
          {selected && !isLoading && !isDisabled && (
            <Button
              variant="plain"
              onClick={(e) => {
                e.stopPropagation()
                clear()
              }}
              aria-label="Clear selection"
            >
              <RhUiCloseIcon />
            </Button>
          )}
        </TextInputGroupUtilities>
      </TextInputGroup>
    </MenuToggle>
  )

  const noResultsText = isLoading ? 'Loading...' : `No results match "${filterValue}"`

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterValue('')
  }

  return (
    <SynSelect
      id={id}
      aria-label={ariaLabel}
      isOpen={isMenuOpen}
      onOpenChange={handleOpenChange}
      onSelect={onSelect}
      selected={selected}
      toggle={toggle}
    >
      <SelectList style={{ maxHeight: '200px', overflow: 'auto' }}>
        {options.length === 0 ? (
          <SelectOption isDisabled>{noResultsText}</SelectOption>
        ) : (
          options.map((option) => (
            <SelectOption
              key={option.value}
              value={option.value}
              isSelected={option.value === selected}
              description={option.description}
            >
              {option.label}
            </SelectOption>
          ))
        )}
      </SelectList>
    </SynSelect>
  )
}
