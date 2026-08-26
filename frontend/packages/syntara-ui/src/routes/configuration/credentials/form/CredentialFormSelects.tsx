import { MenuToggle, type MenuToggleElement, SelectList, SelectOption, Spinner } from '@patternfly/react-core'
import { useState, type Ref } from 'react'

import { LONG_SELECT_MAX_MENU_HEIGHT, longSelectMenuPopperProps } from '../../../../components/longSelectMenu'
import longSelectMenuStyles from '../../../../components/longSelectMenu.module.css'
import { SynSelect } from '../../../../components/SynSelect'

export function ProjectSelect({
  value,
  onChange,
  projects,
  isDisabled,
  isLoading,
  validated,
}: {
  value: string
  onChange: (value: string) => void
  projects: Array<{ id?: string; name: string }>
  isDisabled?: boolean
  isLoading?: boolean
  validated?: 'error' | 'default'
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = projects.find((p) => p.id === value)?.name
  const toggleText = isLoading ? 'Loading projects...' : (selectedLabel ?? 'Select a project')
  return (
    <SynSelect
      id="credential-project"
      isOpen={isOpen}
      selected={value || undefined}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      isScrollable
      maxMenuHeight={LONG_SELECT_MAX_MENU_HEIGHT}
      popperProps={longSelectMenuPopperProps}
      className={longSelectMenuStyles.containScroll}
      toggle={(toggleRef: Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isDisabled={isDisabled}
          isPlaceholder={!value}
          status={validated === 'error' ? 'danger' : undefined}
          aria-label="Credential project"
        >
          {isLoading ? (
            <>
              <Spinner size="sm" aria-label="Loading projects" /> {toggleText}
            </>
          ) : (
            toggleText
          )}
        </MenuToggle>
      )}
    >
      <SelectList>
        {projects.map((p) => (
          <SelectOption key={p.id} value={p.id}>
            {p.name}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

type CredentialType = { id?: string; name?: string }

export function CredentialTypeSelect({
  types,
  selectedTypeId,
  onSelect,
  isDisabled,
  isLoading,
  hasError,
}: {
  types: CredentialType[]
  selectedTypeId: string
  onSelect: (event: React.MouseEvent | undefined, value: string | number | undefined) => void
  isDisabled?: boolean
  isLoading?: boolean
  hasError?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = types.find((t) => t.id === selectedTypeId)?.name
  const toggleText = isLoading ? 'Loading types...' : (selectedLabel ?? 'Select a credential type')

  return (
    <SynSelect
      id="credential-type"
      isOpen={isOpen}
      selected={selectedTypeId || undefined}
      onSelect={(_event, val: string | number | undefined) => {
        onSelect(_event, val)
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      shouldFocusToggleOnSelect
      isScrollable
      maxMenuHeight={LONG_SELECT_MAX_MENU_HEIGHT}
      popperProps={longSelectMenuPopperProps}
      className={longSelectMenuStyles.containScroll}
      toggle={(toggleRef: Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isDisabled={isDisabled}
          isFullWidth
          status={hasError ? 'danger' : undefined}
          aria-label="Credential type"
        >
          {isLoading ? (
            <>
              <Spinner size="sm" aria-label="Loading credential types" /> {toggleText}
            </>
          ) : (
            toggleText
          )}
        </MenuToggle>
      )}
    >
      <SelectList aria-label="Credential type options">
        {types.map((t) => (
          <SelectOption key={t.id} value={t.id} isSelected={t.id === selectedTypeId}>
            {t.name}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}
