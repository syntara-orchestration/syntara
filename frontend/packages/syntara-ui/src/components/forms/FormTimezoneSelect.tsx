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
import { useCallback, useMemo, useState } from 'react'

import { getIanaTimezones } from '../../utils/timezoneList'
import { SynSelect } from '../SynSelect'

type FormTimezoneSelectProps = Readonly<{
  id: string
  value: string
  onChange: (timezone: string) => void
  isDisabled?: boolean
  ariaLabel?: string
  allowEmpty?: boolean
  emptyOptionLabel?: string
}>

export function FormTimezoneSelect({
  id,
  value,
  onChange,
  isDisabled,
  ariaLabel = 'Time zone',
  allowEmpty = false,
  emptyOptionLabel = 'No time zone',
}: FormTimezoneSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const timezones = useMemo(() => getIanaTimezones(), [])
  const filtered = filter ? timezones.filter((tz) => tz.toLowerCase().includes(filter.toLowerCase())) : timezones

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, selected: string | number | undefined) => {
      if (selected === undefined) {
        return
      }
      onChange(String(selected))
      setIsOpen(false)
      setFilter('')
    },
    [onChange]
  )

  const toggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        onClick={() => setIsOpen((prev) => !prev)}
        isExpanded={isOpen}
        isFullWidth
        isDisabled={isDisabled}
        aria-label={ariaLabel}
      >
        {value || 'Select time zone'}
      </MenuToggle>
    ),
    [ariaLabel, isDisabled, isOpen, value]
  )

  return (
    <SynSelect
      id={id}
      isOpen={isOpen}
      selected={value}
      onSelect={handleSelect}
      onOpenChange={(open) => {
        setIsOpen(open)
        if (!open) {
          setFilter('')
        }
      }}
      toggle={toggle}
      aria-label={ariaLabel}
    >
      <TextInputGroup>
        <TextInputGroupMain
          value={filter}
          onChange={(_event, val) => setFilter(val)}
          placeholder="Filter timezones"
          aria-label="Filter timezones"
        />
        {filter && (
          <TextInputGroupUtilities>
            <Button variant="plain" onClick={() => setFilter('')} aria-label="Clear timezone filter">
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        )}
      </TextInputGroup>
      <SelectList aria-label="Timezone options">
        {allowEmpty && <SelectOption value="">{emptyOptionLabel}</SelectOption>}
        {filtered.slice(0, 50).map((tz) => (
          <SelectOption key={tz} value={tz}>
            {tz}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}
