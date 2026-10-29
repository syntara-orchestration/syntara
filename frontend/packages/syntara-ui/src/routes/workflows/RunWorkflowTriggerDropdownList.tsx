import { DropdownGroup, DropdownItem, DropdownList } from '@patternfly/react-core'

export type RunWorkflowTriggerDropdownOption = Readonly<{
  id: string
  label: string
}>

type RunWorkflowTriggerDropdownListProps = Readonly<{
  options: RunWorkflowTriggerDropdownOption[]
  onSelect: (option: RunWorkflowTriggerDropdownOption) => void
}>

/** Menu list for choosing which workflow trigger to run (matches builder Run dropdown). */
export function RunWorkflowTriggerDropdownList({ options, onSelect }: RunWorkflowTriggerDropdownListProps) {
  return (
    <DropdownGroup label="Run workflow">
      <DropdownList>
        {options.map((option) => (
          <DropdownItem key={option.id} onClick={() => onSelect(option)}>
            {option.label}
          </DropdownItem>
        ))}
      </DropdownList>
    </DropdownGroup>
  )
}
