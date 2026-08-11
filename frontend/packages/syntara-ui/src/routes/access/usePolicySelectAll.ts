import { useCallback, useRef, useState } from 'react'

import { detachPromise } from '../../utils/detachPromise'

import { mergeSelectAll, SELECT_ALL_LOAD_ERROR, type PolicySelectListItem } from './policySelectConstants'

type ShowError = (alert: { title: string; description?: string }) => void

type UsePolicySelectAllParams = {
  selected: string[]
  onChange: (selected: string[]) => void
  fetchPolicies: () => Promise<PolicySelectListItem[]>
  showError: ShowError
  onAfterSelect?: () => void
}

export function usePolicySelectAll({
  selected,
  onChange,
  fetchPolicies,
  showError,
  onAfterSelect,
}: UsePolicySelectAllParams) {
  const [isSelectingAll, setIsSelectingAll] = useState(false)
  const isSelectingAllRef = useRef(false)

  const runSelectAll = useCallback(() => {
    if (isSelectingAllRef.current) return

    isSelectingAllRef.current = true
    setIsSelectingAll(true)
    detachPromise(
      fetchPolicies()
        .then((policies) => {
          onChange(mergeSelectAll(selected, policies.map((policy) => policy.name)))
          onAfterSelect?.()
        })
        .catch(() => {
          showError(SELECT_ALL_LOAD_ERROR)
        })
        .finally(() => {
          isSelectingAllRef.current = false
          setIsSelectingAll(false)
        })
    )
  }, [fetchPolicies, onAfterSelect, onChange, selected, showError])

  return { isSelectingAll, runSelectAll }
}
