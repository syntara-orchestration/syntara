import { DropdownGroup, DropdownItem, DropdownList } from '@patternfly/react-core'

export type RunWorkflowTriggerDropdownOption = Readonly<{
  id: string
  label: string
}>

type RunWorkflowTriggerDropdownListProps = Readonly<{
  options: RunWorkflowTriggerDropdownOption[]
  onSelect: (option: RunWorkflowTriggerDropdownOption) => void
  /** When set, wraps items in a labeled dropdown group (e.g. builder Run menu). Omit for a flat list. */
  groupLabel?: string
}>

/** Menu list for choosing which workflow trigger to run inside a PatternFly Dropdown. */
export function RunWorkflowTriggerDropdownList({ options, onSelect, groupLabel }: RunWorkflowTriggerDropdownListProps) {
  const list = (
    <DropdownList>
      {options.map((option) => (
        <DropdownItem key={option.id} onClick={() => onSelect(option)}>
          {option.label}
        </DropdownItem>
      ))}
    </DropdownList>
  )

  if (groupLabel) {
    return <DropdownGroup label={groupLabel}>{list}</DropdownGroup>
  }

  return list
}
