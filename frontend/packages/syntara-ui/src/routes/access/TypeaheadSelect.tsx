import {
  Button,
  Flex,
  FlexItem,
  Label,
  MenuToggle,
  SelectList,
  SelectOption,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { type Ref, useCallback, useMemo, useRef, useState } from 'react'

import { SynSelect } from '../../components/SynSelect'

export type TypeaheadOptionTag = {
  label: string
  color: 'blue' | 'green' | 'orange' | 'orangered' | 'red' | 'purple' | 'grey' | 'teal' | 'yellow'
}

export type TypeaheadOption = {
  value: string
  label: string
  description?: string
  tag?: TypeaheadOptionTag
}

type TypeaheadSelectProps = {
  id: string
  ariaLabel: string
  options: TypeaheadOption[]
  selected: string
  onChange: (value: string) => void
  placeholder?: string
  hasError?: boolean
  isDisabled?: boolean
  /** When provided, filtering is delegated to the caller (server-side search). */
  onSearchChange?: (term: string) => void
  /** Shows a footer hint when the server has more results beyond the current page. */
  hasMore?: boolean
  /** Shows a loading indicator while fetching results. */
  isLoading?: boolean
}

function renderOptions(
  options: TypeaheadOption[],
  filterValue: string,
  selected: string,
  hasMore?: boolean,
  isLoading?: boolean
) {
  if (isLoading) {
    return <SelectOption isDisabled>Loading...</SelectOption>
  }
  if (options.length === 0) {
    return <SelectOption isDisabled>No results match &quot;{filterValue}&quot;</SelectOption>
  }
  return (
    <>
      {options.map((option) => (
        <SelectOption
          key={option.value}
          value={option.value}
          isSelected={option.value === selected}
          description={option.description}
        >
          {option.tag ? (
            <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
              <FlexItem>
                <Label isCompact color={option.tag.color}>
                  {option.tag.label}
                </Label>
              </FlexItem>
              <FlexItem>{option.label}</FlexItem>
            </Flex>
          ) : (
            option.label
          )}
        </SelectOption>
      ))}
      {hasMore && <SelectOption isDisabled>Type to narrow results...</SelectOption>}
    </>
  )
}

export function TypeaheadSelect({
  id,
  ariaLabel,
  options,
  selected,
  onChange,
  placeholder = 'Select...',
  hasError,
  isDisabled,
  onSearchChange,
  hasMore,
  isLoading,
}: Readonly<TypeaheadSelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const selectedLabel = options.find((o) => o.value === selected)?.label ?? ''

  const isServerFiltered = !!onSearchChange

  const filteredOptions = useMemo(() => {
    if (isServerFiltered) return options
    if (!filterValue) return options
    const term = filterValue.toLowerCase()
    return options.filter((o) => o.label.toLowerCase().includes(term))
  }, [options, filterValue, isServerFiltered])

  const handleFilterChange = (val: string) => {
    setFilterValue(val)
    if (onSearchChange) {
      onSearchChange(val)
    }
  }

  const onSelect = (_event: React.MouseEvent<Element, MouseEvent> | undefined, value: string | number | undefined) => {
    if (value === undefined) return
    onChange(String(value))
    setFilterValue('')
    if (onSearchChange) {
      onSearchChange('')
    }
    setIsOpen(false)
  }

  const clear = () => {
    onChange('')
    setFilterValue('')
    if (onSearchChange) {
      onSearchChange('')
    }
    inputRef.current?.focus()
  }

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      onClick={() => setIsOpen(!isOpen)}
      isExpanded={isOpen}
      isFullWidth
      isDisabled={isDisabled}
      status={hasError ? 'danger' : undefined}
    >
      <TextInputGroup isPlain isDisabled={isDisabled}>
        <TextInputGroupMain
          value={isOpen ? filterValue : selectedLabel}
          onChange={(_e, val) => {
            handleFilterChange(val)
            if (!isOpen) setIsOpen(true)
          }}
          onClick={() => {
            if (!isOpen) setIsOpen(true)
          }}
          placeholder={placeholder}
          autoComplete="off"
          innerRef={inputRef}
        />
        {selected && (
          <TextInputGroupUtilities>
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
          </TextInputGroupUtilities>
        )}
      </TextInputGroup>
    </MenuToggle>
  )

  const handleOpenChange = useCallback(
    (open: boolean) => {
      setIsOpen(open)
      if (!open) {
        setFilterValue('')
        onSearchChange?.('')
      }
    },
    [onSearchChange]
  )

  return (
    <SynSelect
      id={id}
      aria-label={ariaLabel}
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={onSelect}
      selected={selected}
      toggle={toggle}
    >
      <SelectList style={{ maxHeight: '200px', overflow: 'auto' }}>
        {renderOptions(filteredOptions, filterValue, selected, hasMore, isLoading)}
      </SelectList>
    </SynSelect>
  )
}
