import { FormGroup, MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import { useState, useCallback } from 'react'

import { FormLabelWithHelp } from '../../../../components/FormLabelWithHelp'
import { SynSelect } from '../../../../components/SynSelect'

import type { ExclusiveGroup } from './credentialFormUtils'

type AuthMethodSelectorProps = {
  groups: ExclusiveGroup[]
  activeIndex: number
  onChange: (index: number) => void
  helpText?: string
}

type AuthMethodToggleProps = {
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  onToggle: () => void
  label: string
}

function AuthMethodToggle({ toggleRef, isOpen, onToggle, label }: Readonly<AuthMethodToggleProps>) {
  return (
    <MenuToggle ref={toggleRef} onClick={onToggle} isExpanded={isOpen} isFullWidth aria-label="Auth method">
      {label}
    </MenuToggle>
  )
}

export function AuthMethodSelector({ groups, activeIndex, onChange, helpText }: Readonly<AuthMethodSelectorProps>) {
  const [isOpen, setIsOpen] = useState(false)

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      onChange(Number(value))
      setIsOpen(false)
    },
    [onChange]
  )

  const handleToggle = useCallback(() => setIsOpen((prev) => !prev), [])

  const toggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <AuthMethodToggle
        toggleRef={toggleRef}
        isOpen={isOpen}
        onToggle={handleToggle}
        label={groups[activeIndex]?.label ?? 'Select auth method'}
      />
    ),
    [isOpen, handleToggle, groups, activeIndex]
  )

  const label = helpText ? <FormLabelWithHelp label="Auth method" helpText={helpText} /> : 'Auth method'

  return (
    <FormGroup label={label} fieldId="auth-method" isRequired>
      <SynSelect
        id="auth-method"
        isOpen={isOpen}
        selected={String(activeIndex)}
        onSelect={handleSelect}
        onOpenChange={setIsOpen}
        toggle={toggle}
        shouldFocusToggleOnSelect
        popperProps={{ appendTo: 'inline' }}
      >
        <SelectList>
          {groups.map((group, index) => (
            <SelectOption key={group.label} value={String(index)}>
              {group.label}
            </SelectOption>
          ))}
        </SelectList>
      </SynSelect>
    </FormGroup>
  )
}
