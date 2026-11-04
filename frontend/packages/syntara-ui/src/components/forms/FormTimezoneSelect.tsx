import {
  Button,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { type MouseEvent, type Ref, useCallback, useMemo, useRef, useState } from 'react'

import { getIanaTimezones } from '../../utils/timezoneList'
import { SynSelect } from '../SynSelect'

/** Props for an optional, searchable IANA timezone selector. */
type FormTimezoneSelectProps = Readonly<{
  /** ID applied to the typeahead input. */
  id: string
  /** Selected IANA timezone, or an empty string when no timezone is selected. */
  value: string
  /** Called with the selected timezone, or an empty string when cleared. */
  onChange: (timezone: string) => void
  /** Disables the selector and its clear action. */
  isDisabled?: boolean
  /** Accessible name for the timezone input and select. */
  ariaLabel?: string
}>

export function FormTimezoneSelect({
  id,
  value,
  onChange,
  isDisabled,
  ariaLabel = 'Time zone',
}: FormTimezoneSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const timezones = useMemo(() => getIanaTimezones(), [])
  const filtered = filter ? timezones.filter((tz) => tz.toLowerCase().includes(filter.toLowerCase())) : timezones

  const handleSelect = useCallback(
    (_event: MouseEvent<Element> | undefined, selected: string | number | undefined) => {
      if (selected === undefined) {
        return
      }
      onChange(String(selected))
      setIsOpen(false)
      setFilter('')
    },
    [onChange]
  )

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) {
      setFilter('')
    }
  }, [])

  const toggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        variant="typeahead"
        onClick={() => setIsOpen((previous) => !previous)}
        isExpanded={isOpen}
        isFullWidth
        isDisabled={isDisabled}
        aria-label={ariaLabel}
      >
        <TextInputGroup isPlain isDisabled={isDisabled}>
          <TextInputGroupMain
            inputId={id}
            value={isOpen ? filter : value}
            onChange={(_event, nextFilter) => {
              setFilter(nextFilter)
              if (!isOpen) {
                setIsOpen(true)
              }
            }}
            onClick={(event) => {
              event.stopPropagation()
              if (!isOpen) {
                setIsOpen(true)
              }
            }}
            placeholder="Select time zone"
            aria-label={ariaLabel}
            autoComplete="off"
            innerRef={inputRef}
          />
          {(value || filter) && !isDisabled && (
            <TextInputGroupUtilities>
              <Button
                variant="plain"
                onClick={(event) => {
                  event.stopPropagation()
                  onChange('')
                  setFilter('')
                  inputRef.current?.focus()
                }}
                aria-label="Clear time zone"
              >
                <RhUiCloseIcon />
              </Button>
            </TextInputGroupUtilities>
          )}
        </TextInputGroup>
      </MenuToggle>
    ),
    [ariaLabel, filter, id, isDisabled, isOpen, onChange, value]
  )

  return (
    <SynSelect
      id={id}
      aria-label={ariaLabel}
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={handleSelect}
      selected={value}
      shouldFocusToggleOnSelect={false}
      toggle={toggle}
    >
      <SelectList aria-label="Time zone options">
        {filtered.length === 0 ? (
          <SelectOption isDisabled>No time zones match &quot;{filter}&quot;</SelectOption>
        ) : (
          filtered.slice(0, 50).map((timezone) => (
            <SelectOption key={timezone} value={timezone} isSelected={timezone === value}>
              {timezone}
            </SelectOption>
          ))
        )}
      </SelectList>
    </SynSelect>
  )
}
