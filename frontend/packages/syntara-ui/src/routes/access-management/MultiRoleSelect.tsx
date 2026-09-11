import {
  Button,
  Label,
  LabelGroup,
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

import styles from './AssignRoleModal.module.css'

export type RoleOption = {
  id: string
  name: string
  description: string | null
}

function renderSelectOptions(options: RoleOption[], filterValue: string, hasMore?: boolean, isLoading?: boolean) {
  if (isLoading) {
    return <SelectOption isDisabled>Loading...</SelectOption>
  }
  if (options.length === 0 && !hasMore) {
    return (
      <SelectOption isDisabled>{filterValue ? `No results match "${filterValue}"` : 'No roles available'}</SelectOption>
    )
  }
  return (
    <>
      {options.map((role) => (
        <SelectOption key={role.id} value={role.id} description={role.description ?? undefined}>
          {role.name}
        </SelectOption>
      ))}
      {hasMore && <SelectOption isDisabled>Type to narrow results...</SelectOption>}
    </>
  )
}

export function MultiRoleSelect({
  options,
  selected,
  onChange,
  onSearchChange,
  hasMore,
  isLoading,
  hasError,
}: Readonly<{
  options: RoleOption[]
  selected: string[]
  onChange: (ids: string[]) => void
  onSearchChange?: (term: string) => void
  hasMore?: boolean
  isLoading?: boolean
  hasError?: boolean
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const isServerFiltered = !!onSearchChange

  const filteredOptions = useMemo(() => {
    const available = options.filter((o) => !selected.includes(o.id))
    if (isServerFiltered || !filterValue) return available
    const term = filterValue.toLowerCase()
    return available.filter((o) => o.name.toLowerCase().includes(term))
  }, [options, selected, filterValue, isServerFiltered])

  const selectedLabels = useMemo(() => {
    const map = new Map(options.map((o) => [o.id, o.name]))
    return selected.map((id) => ({ id, name: map.get(id) ?? id }))
  }, [options, selected])

  const handleSelect = (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
    if (!value) return
    const roleId = String(value)
    if (!selected.includes(roleId)) {
      onChange([...selected, roleId])
    }
    setFilterValue('')
    if (onSearchChange) onSearchChange('')
    inputRef.current?.focus()
  }

  const handleRemove = (roleId: string) => {
    onChange(selected.filter((id) => id !== roleId))
  }

  const handleClear = () => {
    onChange([])
    setFilterValue('')
    if (onSearchChange) onSearchChange('')
    inputRef.current?.focus()
  }

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      onClick={() => setIsOpen(!isOpen)}
      isExpanded={isOpen}
      isFullWidth
      status={hasError ? 'danger' : undefined}
    >
      <TextInputGroup isPlain>
        <TextInputGroupMain
          value={filterValue}
          onChange={(_e, val) => {
            setFilterValue(val)
            if (onSearchChange) onSearchChange(val)
            if (!isOpen) setIsOpen(true)
          }}
          onClick={() => {
            if (!isOpen) setIsOpen(true)
          }}
          placeholder={selected.length === 0 ? 'Search for roles...' : ''}
          autoComplete="off"
          innerRef={inputRef}
        >
          {selectedLabels.length > 0 && (
            <LabelGroup>
              {selectedLabels.map((role) => (
                <Label
                  key={role.id}
                  color="blue"
                  onClose={(e) => {
                    e.stopPropagation()
                    handleRemove(role.id)
                  }}
                >
                  {role.name}
                </Label>
              ))}
            </LabelGroup>
          )}
        </TextInputGroupMain>
        {selected.length > 0 && (
          <TextInputGroupUtilities>
            <Button
              variant="plain"
              onClick={(e) => {
                e.stopPropagation()
                handleClear()
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
      id="multi-role-select"
      aria-label="Select roles"
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={handleSelect}
      toggle={toggle}
    >
      <SelectList className={styles.rolesList}>
        {renderSelectOptions(filteredOptions, filterValue, hasMore, isLoading)}
      </SelectList>
    </SynSelect>
  )
}
