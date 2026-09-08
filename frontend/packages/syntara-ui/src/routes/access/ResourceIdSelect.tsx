import {
  MenuToggle,
  SelectList,
  SelectOption,
  TextInput,
  TextInputGroup,
  TextInputGroupMain,
} from '@patternfly/react-core'
import { type Ref, useEffect, useMemo, useState } from 'react'

import { SynSelect } from '../../components/SynSelect'

import { dynamicFetchClient } from './accessClient'
import { RESOURCE_ENDPOINTS, type ResourceOption } from './canIUtils'

function toStringField(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return ''
}

function parseResourceItems(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[]
  if (typeof data === 'object' && data !== null && 'resources' in data) {
    const resources = (data as { resources?: unknown }).resources
    if (Array.isArray(resources)) return resources as Record<string, unknown>[]
  }
  return []
}

function useResourceOptions(resourceType: string): ResourceOption[] {
  const [options, setOptions] = useState<ResourceOption[]>([])

  useEffect(() => {
    const endpoint = RESOURCE_ENDPOINTS[resourceType]
    if (!endpoint) return

    let cancelled = false

    dynamicFetchClient
      .GET(endpoint.path, {})
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) {
          setOptions([])
          return
        }
        const items = parseResourceItems(data)
        setOptions(
          items
            .map((item) => ({
              id: toStringField(item[endpoint.idField]),
              label: toStringField(item[endpoint.labelField]) || toStringField(item[endpoint.idField]),
            }))
            .sort((a, b) => a.label.localeCompare(b.label))
        )
      })
      .catch(() => {
        if (!cancelled) setOptions([])
      })

    return () => {
      cancelled = true
    }
  }, [resourceType])

  if (!(resourceType in RESOURCE_ENDPOINTS)) return []
  return options
}

type ResourceIdSelectProps = {
  resourceType: string
  value: string
  onChange: (value: string) => void
}

export function ResourceIdSelect({ resourceType, value, onChange }: Readonly<ResourceIdSelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterText, setFilterText] = useState('')
  const allOptions = useResourceOptions(resourceType)
  const hasEndpoint = resourceType in RESOURCE_ENDPOINTS

  const filtered = useMemo(() => {
    if (!filterText.trim()) return allOptions.slice(0, 20)
    const term = filterText.toLowerCase()
    return allOptions
      .filter((o) => o.label.toLowerCase().includes(term) || o.id.toLowerCase().includes(term))
      .slice(0, 20)
  }, [allOptions, filterText])

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterText('')
  }

  if (!hasEndpoint) {
    return (
      <TextInput
        id="can-i-resource-id"
        aria-label="Resource ID"
        value={value}
        onChange={(_e, val) => onChange(val)}
        placeholder="Enter resource ID"
      />
    )
  }

  const displayValue = value ? (allOptions.find((o) => o.id === value)?.label ?? value) : ''

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <MenuToggle ref={toggleRef} variant="typeahead" onClick={() => setIsOpen(!isOpen)} isExpanded={isOpen} isFullWidth>
      <TextInputGroup isPlain>
        <TextInputGroupMain
          value={isOpen ? filterText : displayValue}
          onChange={(_e, val) => {
            setFilterText(val)
            if (!isOpen) setIsOpen(true)
          }}
          onClick={() => {
            if (!isOpen) setIsOpen(true)
          }}
          placeholder={`Search ${resourceType}s...`}
          autoComplete="off"
        />
      </TextInputGroup>
    </MenuToggle>
  )

  return (
    <SynSelect
      id="can-i-resource-id"
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={(_event, selection) => {
        onChange(String(selection))
        setFilterText('')
        setIsOpen(false)
      }}
      selected={value}
      toggle={toggle}
    >
      <SelectList>
        {value && (
          <SelectOption value="" description="Clear selection">
            — None —
          </SelectOption>
        )}
        {filtered.length === 0 ? (
          <SelectOption isDisabled value="__empty__">
            {allOptions.length === 0 ? `No ${resourceType}s found` : 'No matches'}
          </SelectOption>
        ) : (
          filtered.map((o) => (
            <SelectOption key={o.id} value={o.id} description={o.id === o.label ? undefined : o.id}>
              {o.label}
            </SelectOption>
          ))
        )}
      </SelectList>
    </SynSelect>
  )
}
