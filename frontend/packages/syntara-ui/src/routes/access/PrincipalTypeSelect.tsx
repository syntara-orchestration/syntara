import { MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import { useState } from 'react'

import { SynSelect } from '../../components/SynSelect'
import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

const principalTypeLabels: Record<string, string> = {
  [RolePrincipalType.USER]: 'User',
  [RolePrincipalType.GROUP]: 'Group',
  [RolePrincipalType.SERVICE_ACCOUNT]: 'Service Account',
}

export function PrincipalTypeSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <SynSelect
      id="principal-type"
      isOpen={isOpen}
      selected={value}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          aria-label="Principal type"
        >
          {principalTypeLabels[value] ?? value}
        </MenuToggle>
      )}
    >
      <SelectList>
        <SelectOption value={RolePrincipalType.USER}>User</SelectOption>
        <SelectOption value={RolePrincipalType.GROUP}>Group</SelectOption>
        <SelectOption value={RolePrincipalType.SERVICE_ACCOUNT}>Service Account</SelectOption>
      </SelectList>
    </SynSelect>
  )
}
