import {
  Button,
  LabelGroup,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  TextInputGroup,
  TextInputGroupMain,
  TextInputGroupUtilities,
} from '@patternfly/react-core'
import { RhUiCloseIcon } from '@patternfly/react-icons'
import { type Ref, useCallback, useMemo, useRef, useState } from 'react'

import { SynLabel } from '../../../../components/labels/SynLabel'
import { SynSelect } from '../../../../components/SynSelect'
import { useSelectableProjects } from '../../../access/useAllProjects'

type ProjectMultiSelectProps = Readonly<{
  selectedIds: string[]
  onChange: (ids: string[]) => void
  validated?: 'error' | 'default'
}>

function ProjectSelectToggle({
  toggleRef,
  isOpen,
  onClick,
  filterValue,
  onFilterChange,
  onFilterClick,
  selectedLabels,
  onRemove,
  onClear,
  inputRef,
  validated,
}: Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isOpen: boolean
  onClick: () => void
  filterValue: string
  onFilterChange: (value: string) => void
  onFilterClick: () => void
  selectedLabels: { id: string; name: string }[]
  onRemove: (id: string) => void
  onClear: () => void
  inputRef: React.RefObject<HTMLInputElement | null>
  validated?: 'error' | 'default'
}>) {
  return (
    <MenuToggle
      ref={toggleRef}
      variant="typeahead"
      onClick={onClick}
      isExpanded={isOpen}
      isFullWidth
      status={validated === 'error' ? 'danger' : undefined}
    >
      <TextInputGroup isPlain>
        <TextInputGroupMain
          value={filterValue}
          onChange={(_e, val) => onFilterChange(val)}
          onClick={onFilterClick}
          placeholder={selectedLabels.length === 0 ? 'Select projects...' : ''}
          autoComplete="off"
          innerRef={inputRef}
        >
          {selectedLabels.length > 0 && (
            <LabelGroup>
              {selectedLabels.map((project) => (
                <SynLabel
                  key={project.id}
                  color="blue"
                  onClose={(e) => {
                    e.stopPropagation()
                    onRemove(project.id)
                  }}
                >
                  {project.name}
                </SynLabel>
              ))}
            </LabelGroup>
          )}
        </TextInputGroupMain>
        {selectedLabels.length > 0 && (
          <TextInputGroupUtilities>
            <Button
              variant="plain"
              onClick={(e) => {
                e.stopPropagation()
                onClear()
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
}

function projectSelectToggle(
  toggleRef: Ref<MenuToggleElement>,
  state: Omit<Parameters<typeof ProjectSelectToggle>[0], 'toggleRef'>
) {
  return <ProjectSelectToggle toggleRef={toggleRef} {...state} />
}

function renderProjectOptions(
  options: { id: string; name: string }[],
  filterValue: string,
  isLoading: boolean,
  selectedIds: string[]
) {
  if (isLoading) return <SelectOption isDisabled>Loading projects...</SelectOption>
  if (options.length === 0) {
    return (
      <SelectOption isDisabled>
        {filterValue ? `No results match "${filterValue}"` : 'No projects available'}
      </SelectOption>
    )
  }
  return options.map((project) => (
    <SelectOption key={project.id} value={project.id} hasCheckbox isSelected={selectedIds.includes(project.id)}>
      {project.name}
    </SelectOption>
  ))
}

export function ProjectMultiSelect({ selectedIds, onChange, validated }: ProjectMultiSelectProps) {
  const { projects, isLoading } = useSelectableProjects()
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterValue('')
  }, [])

  const filteredOptions = useMemo(() => {
    const available = projects.filter((p): p is typeof p & { id: string } => !!p.id)
    if (!filterValue) return available.map((p) => ({ id: p.id, name: p.name }))
    const term = filterValue.toLowerCase()
    return available.filter((p) => p.name.toLowerCase().includes(term)).map((p) => ({ id: p.id, name: p.name }))
  }, [projects, filterValue])

  const selectedLabels = useMemo(() => {
    const map = new Map(projects.filter((p) => p.id).map((p) => [p.id, p.name]))
    return selectedIds.map((id) => ({ id, name: map.get(id) ?? id }))
  }, [projects, selectedIds])

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, value: string | number | undefined) => {
      if (value === undefined || value === null) return
      const projectId = String(value)
      const newIds = selectedIds.includes(projectId)
        ? selectedIds.filter((id) => id !== projectId)
        : [...selectedIds, projectId]
      onChange(newIds)
      setFilterValue('')
      inputRef.current?.focus()
    },
    [selectedIds, onChange]
  )

  const handleRemove = useCallback(
    (projectId: string) => {
      onChange(selectedIds.filter((id) => id !== projectId))
    },
    [selectedIds, onChange]
  )

  const handleClear = useCallback(() => {
    onChange([])
    setFilterValue('')
    inputRef.current?.focus()
  }, [onChange])

  const toggleState = useMemo(
    () => ({
      isOpen,
      onClick: () => setIsOpen(!isOpen),
      filterValue,
      onFilterChange: (val: string) => {
        setFilterValue(val)
        if (!isOpen) setIsOpen(true)
      },
      onFilterClick: () => {
        if (!isOpen) setIsOpen(true)
      },
      selectedLabels,
      onRemove: handleRemove,
      onClear: handleClear,
      inputRef,
      validated,
    }),
    [isOpen, filterValue, selectedLabels, handleRemove, handleClear, validated]
  )

  const renderToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => projectSelectToggle(toggleRef, toggleState),
    [toggleState]
  )

  return (
    <SynSelect
      aria-label="Select projects"
      isOpen={isOpen}
      selected={selectedIds}
      onSelect={handleSelect}
      onOpenChange={handleOpenChange}
      toggle={renderToggle}
      isScrollable
      maxMenuHeight="200px"
    >
      <SelectList>{renderProjectOptions(filteredOptions, filterValue, isLoading, selectedIds)}</SelectList>
    </SynSelect>
  )
}
