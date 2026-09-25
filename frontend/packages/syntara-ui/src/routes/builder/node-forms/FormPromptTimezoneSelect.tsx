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
import { useCallback, useMemo, useState, type Ref } from 'react'

import { SynSelect } from '../../../components/SynSelect'

let cachedTimezones: string[] | null = null

function getTimezones(): string[] {
  if (!cachedTimezones) {
    try {
      cachedTimezones = Intl.supportedValuesOf('timeZone')
    } catch {
      cachedTimezones = ['UTC']
    }
  }
  return cachedTimezones
}

type FormPromptTimezoneSelectProps = Readonly<{
  value: string
  onChange: (timezone: string) => void
  isDisabled?: boolean
  id?: string
}>

export function FormPromptTimezoneSelect({
  value,
  onChange,
  isDisabled = false,
  id = 'form-prompt-timezone',
}: FormPromptTimezoneSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const filteredTimezones = useMemo(() => {
    const list = getTimezones()
    const query = filter.trim().toLowerCase()
    if (!query) return list
    return list.filter((tz) => tz.toLowerCase().includes(query))
  }, [filter])

  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        id={id}
        onClick={() => setIsOpen((prev) => !prev)}
        isExpanded={isOpen}
        isFullWidth
        isDisabled={isDisabled}
        aria-label="Timezone for date fields"
      >
        {value || 'UTC'}
      </MenuToggle>
    ),
    [id, isDisabled, isOpen, value]
  )

  return (
    <SynSelect
      id={`${id}-select`}
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, selected) => {
        if (typeof selected === 'string' && selected.length > 0) {
          onChange(selected)
        }
        setIsOpen(false)
        setFilter('')
      }}
      onOpenChange={(open) => {
        setIsOpen(open)
        if (!open) setFilter('')
      }}
      toggle={renderToggle}
    >
      <TextInputGroup>
        <TextInputGroupMain
          value={filter}
          onChange={(_event, val) => setFilter(val)}
          placeholder="Filter timezones"
          aria-label="Filter timezones"
        />
        {filter ? (
          <TextInputGroupUtilities>
            <Button variant="plain" onClick={() => setFilter('')} aria-label="Clear timezone filter">
              <RhUiCloseIcon />
            </Button>
          </TextInputGroupUtilities>
        ) : null}
      </TextInputGroup>
      <SelectList aria-label="Timezone options">
        {filteredTimezones.slice(0, 50).map((tz) => (
          <SelectOption key={tz} value={tz}>
            {tz}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}
