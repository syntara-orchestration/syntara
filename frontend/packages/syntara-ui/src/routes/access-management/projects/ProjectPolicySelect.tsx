import { type Ref, useCallback, useMemo, useRef, useState } from 'react'

import { LONG_SELECT_MAX_MENU_HEIGHT, longSelectMenuPopperProps } from '../../../components/longSelectMenu'
import longSelectMenuStyles from '../../../components/longSelectMenu.module.css'
import { NxSelect } from '../../../components/NxSelect'
import { useAlerts } from '../../../providers/alerts'
import { accessClient } from '../../access/accessClient'
import { fetchAllProjectPoliciesForSelect } from '../../access/fetchAllPoliciesForSelect'
import { SELECT_ALL_VALUE } from '../../access/policySelectConstants'
import { PolicySelectOptionsList } from '../../access/PolicySelectOptionsList'
import { PolicySelectToggle } from '../../access/PolicySelectToggle'
import { usePolicySelectAll } from '../../access/usePolicySelectAll'

type ProjectPolicySelectProps = {
  projectId: string
  selected: string[]
  onChange: (selected: string[]) => void
  hasError?: boolean
}

const PAGE_SIZE = 50

export function ProjectPolicySelect({ projectId, selected, onChange, hasError }: Readonly<ProjectPolicySelectProps>) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const { showError } = useAlerts()

  const policiesQuery = accessClient.useQuery(
    'get',
    '/projects/{project_id}/policies',
    {
      params: {
        path: { project_id: projectId },
        query: { sort: 'name', limit: PAGE_SIZE },
      },
    },
    { enabled: isOpen }
  )

  const policyOptions = useMemo(() => {
    const fetched = policiesQuery.data?.resources ?? []
    const fetchedNames = new Set(fetched.map((p) => p.name))
    const selectedOnly = selected.filter((name) => !fetchedNames.has(name))
    return [
      ...fetched.map((p) => ({ name: p.name, description: p.description ?? null })),
      ...selectedOnly.map((name) => ({ name, description: null })),
    ]
  }, [policiesQuery.data?.resources, selected])

  const filteredOptions = useMemo(() => {
    if (filterValue) {
      const term = filterValue.toLowerCase()
      return policyOptions.filter((p) => p.name.toLowerCase().includes(term))
    }
    return policyOptions
  }, [policyOptions, filterValue])

  const fetchAllMatchingPolicies = useCallback(
    () => fetchAllProjectPoliciesForSelect(projectId, filterValue || undefined),
    [projectId, filterValue]
  )

  const { isSelectingAll, runSelectAll } = usePolicySelectAll({
    selected,
    onChange,
    fetchPolicies: fetchAllMatchingPolicies,
    showError,
    onAfterSelect: () => {
      setFilterValue('')
      inputRef.current?.focus()
    },
  })

  const onSelect = useCallback(
    (_event: React.MouseEvent<Element, MouseEvent> | undefined, value: string | number | undefined) => {
      if (value === SELECT_ALL_VALUE) {
        runSelectAll()
        return
      }

      const policyName = value as string
      if (selected.includes(policyName)) {
        onChange(selected.filter((p) => p !== policyName))
      } else {
        onChange([...selected, policyName])
      }
      setFilterValue('')
      inputRef.current?.focus()
    },
    [selected, onChange, runSelectAll]
  )

  const removePolicy = useCallback(
    (policyName: string) => {
      onChange(selected.filter((p) => p !== policyName))
    },
    [selected, onChange]
  )

  const clearAll = useCallback(() => {
    onChange([])
    setFilterValue('')
  }, [onChange])

  const isLoading = policiesQuery.isLoading || policiesQuery.isFetching

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterValue('')
  }, [])

  const openDropdown = useCallback(() => {
    if (!isOpen) setIsOpen(true)
  }, [isOpen])

  const toggle = (toggleRef: Ref<HTMLButtonElement>) => (
    <PolicySelectToggle
      toggleRef={toggleRef}
      isOpen={isOpen}
      onToggle={() => setIsOpen(!isOpen)}
      filterValue={filterValue}
      onFilterChange={(val) => {
        setFilterValue(val)
        openDropdown()
      }}
      onFilterFocus={openDropdown}
      selected={selected}
      onRemovePolicy={removePolicy}
      onClearAll={clearAll}
      inputRef={inputRef}
      hasError={hasError}
      toggleTestId="policy-select-toggle"
    />
  )

  return (
    <NxSelect
      id="project-role-policies"
      aria-label="Policies"
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      onSelect={onSelect}
      selected={selected}
      toggle={toggle}
      isScrollable
      maxMenuHeight={LONG_SELECT_MAX_MENU_HEIGHT}
      popperProps={longSelectMenuPopperProps}
      className={longSelectMenuStyles.containScroll}
    >
      <PolicySelectOptionsList
        isLoading={isLoading}
        filterValue={filterValue}
        filteredOptions={filteredOptions}
        selected={selected}
        isSelectingAll={isSelectingAll}
      />
    </NxSelect>
  )
}
