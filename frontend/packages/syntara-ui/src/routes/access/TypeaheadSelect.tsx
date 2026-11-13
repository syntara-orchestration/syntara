import {
  Button,
  Flex,
  FlexItem,
  Label,
  MenuToggle,
  SelectGroup,
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
  group?: string
  tag?: TypeaheadOptionTag
}

type TypeaheadSelectProps = {
  id: string
  ariaLabel: string
  options: TypeaheadOption[]
  selected: string
  selectedLabel?: string
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
  /** Requires a search term before showing local results above this count. */
  searchPromptThreshold?: number
}

function renderOption(option: TypeaheadOption, selected: string) {
  return (
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
  )
}

function renderOptions({
  options,
  filterValue,
  selected,
  hasMore,
  isLoading,
  shouldPromptForSearch,
}: {
  options: TypeaheadOption[]
  filterValue: string
  selected: string
  hasMore?: boolean
  isLoading?: boolean
  shouldPromptForSearch?: boolean
}) {
  if (isLoading) {
    return <SelectOption isDisabled>Loading...</SelectOption>
  }
  if (options.length === 0) {
    return <SelectOption isDisabled>No results match &quot;{filterValue}&quot;</SelectOption>
  }
  if (shouldPromptForSearch && !filterValue.trim()) {
    return <SelectOption isDisabled>Type to search step and output names...</SelectOption>
  }
  if (options.some((option) => option.group)) {
    const groups = new Map<string, TypeaheadOption[]>()
    for (const option of options) {
      const groupLabel = option.group ?? 'Other outputs'
      const groupOptions = groups.get(groupLabel)
      if (groupOptions) groupOptions.push(option)
      else groups.set(groupLabel, [option])
    }
    return (
      <>
        {[...groups].map(([groupLabel, groupOptions]) => (
          <SelectGroup key={groupLabel} label={groupLabel}>
            {groupOptions.map((option) => renderOption(option, selected))}
          </SelectGroup>
        ))}
        {hasMore && <SelectOption isDisabled>Type to narrow results...</SelectOption>}
      </>
    )
  }
  return (
    <>
      {options.map((option) => renderOption(option, selected))}
      {hasMore && <SelectOption isDisabled>Type to narrow results...</SelectOption>}
    </>
  )
}

export function TypeaheadSelect({
  id,
  ariaLabel,
  options,
  selected,
  selectedLabel: selectedLabelOverride,
  onChange,
  placeholder = 'Select...',
  hasError,
  isDisabled,
  onSearchChange,
  hasMore,
  isLoading,
  searchPromptThreshold,
}: Readonly<TypeaheadSelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const selectedLabel = selectedLabelOverride ?? options.find((option) => option.value === selected)?.label ?? ''

  const isServerFiltered = !!onSearchChange

  const filteredOptions = useMemo(() => {
    if (isServerFiltered) return options
    if (!filterValue) return options
    const term = filterValue.toLowerCase()
    return options.filter((option) =>
      [option.group, option.label, option.description].some((value) => value?.toLowerCase().includes(term))
    )
  }, [options, filterValue, isServerFiltered])
  const shouldPromptForSearch =
    searchPromptThreshold !== undefined && options.length > searchPromptThreshold && !filterValue.trim()

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
          inputId={id}
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
      aria-label={ariaLabel}
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={onSelect}
      selected={selected}
      toggle={toggle}
    >
      <SelectList style={{ maxHeight: '200px', overflow: 'auto' }}>
        {renderOptions({ options: filteredOptions, filterValue, selected, hasMore, isLoading, shouldPromptForSearch })}
      </SelectList>
    </SynSelect>
  )
}
