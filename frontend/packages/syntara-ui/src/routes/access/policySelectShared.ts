import { useCallback, useRef, useState } from 'react'

import { useAlerts } from '../../providers/alerts'

import { SELECT_ALL_VALUE, type PolicySelectListItem } from './policySelectConstants'
import { usePolicySelectAll } from './usePolicySelectAll'

export type PolicySelectOption = {
  name: string
  description: string | null
}

export function buildPolicyOptionList(
  fetched: readonly { name: string; description?: string | null }[],
  selected: string[]
): PolicySelectOption[] {
  const fetchedNames = new Set(fetched.map((policy) => policy.name))
  const selectedOnly = selected.filter((name) => !fetchedNames.has(name))
  return [
    ...fetched.map((policy) => ({ name: policy.name, description: policy.description ?? null })),
    ...selectedOnly.map((name) => ({ name, description: null })),
  ]
}

export function filterPolicyOptionsByTerm(options: PolicySelectOption[], term: string): PolicySelectOption[] {
  if (!term) return options
  const lower = term.toLowerCase()
  return options.filter((policy) => policy.name.toLowerCase().includes(lower))
}

type UsePolicySelectFieldParams = {
  selected: string[]
  onChange: (selected: string[]) => void
  fetchPolicies: () => Promise<PolicySelectListItem[]>
}

export function usePolicySelectField({ selected, onChange, fetchPolicies }: UsePolicySelectFieldParams) {
  const [isOpen, setIsOpen] = useState(false)
  const [filterValue, setFilterValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const { showError } = useAlerts()

  const clearFilterAndFocus = useCallback(() => {
    setFilterValue('')
    inputRef.current?.focus()
  }, [])

  const { isSelectingAll, runSelectAll } = usePolicySelectAll({
    selected,
    onChange,
    fetchPolicies,
    showError,
    onAfterSelect: clearFilterAndFocus,
  })

  const onSelect = useCallback(
    (_event: React.MouseEvent<Element, MouseEvent> | undefined, value: string | number | undefined) => {
      if (value === SELECT_ALL_VALUE) {
        runSelectAll()
        return
      }

      const policyName = value as string
      if (selected.includes(policyName)) {
        onChange(selected.filter((policy) => policy !== policyName))
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
      onChange(selected.filter((policy) => policy !== policyName))
    },
    [selected, onChange]
  )

  const clearAll = useCallback(() => {
    onChange([])
    setFilterValue('')
  }, [onChange])

  const handleOpenChange = useCallback((open: boolean) => {
    setIsOpen(open)
    if (!open) setFilterValue('')
  }, [])

  const openDropdown = useCallback(() => {
    if (!isOpen) setIsOpen(true)
  }, [isOpen])

  return {
    isOpen,
    filterValue,
    setFilterValue,
    inputRef,
    isSelectingAll,
    onSelect,
    removePolicy,
    clearAll,
    handleOpenChange,
    openDropdown,
  }
}
