import { MenuToggle, type MenuToggleElement, SelectList, SelectOption } from '@patternfly/react-core'
import { useState } from 'react'

import { SynSelect } from '../../components/SynSelect'

export function ProjectSelect({
  id,
  value,
  onChange,
  projects,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  projects: Array<{ id?: string; name: string }>
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = projects.find((p) => p.name === value)?.name
  return (
    <SynSelect
      id={id}
      isOpen={isOpen}
      selected={value || undefined}
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
          isPlaceholder={!value}
          aria-label="Project"
        >
          {selectedLabel ?? 'Any project'}
        </MenuToggle>
      )}
    >
      <SelectList>
        <SelectOption value="">Any project</SelectOption>
        {projects.map((p) => (
          <SelectOption key={p.id} value={p.name}>
            {p.name}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}
