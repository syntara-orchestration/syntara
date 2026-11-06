import { useCallback, useMemo, useRef, useState } from 'react'

import { accessClient } from '../../access/accessClient'
import { fetchAllProjectPoliciesForSelect } from '../../access/fetchAllPoliciesForSelect'
import { PolicySelectBase } from '../../access/PolicySelectBase'

type ProjectPolicySelectProps = {
  projectId: string
  selected: string[]
  onChange: (selected: string[]) => void
  hasError?: boolean
}

const PAGE_SIZE = 50

export function ProjectPolicySelect({ projectId, selected, onChange, hasError }: Readonly<ProjectPolicySelectProps>) {
  const filterValueRef = useRef('')
  const [isOpen, setIsOpen] = useState(false)

  const fetchAllMatchingPolicies = useCallback(
    () => fetchAllProjectPoliciesForSelect(projectId, filterValueRef.current || undefined),
    [projectId]
  )

  const handleFilterValueChange = useCallback((value: string) => {
    filterValueRef.current = value
  }, [])

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

  const policyResources = useMemo(() => policiesQuery.data?.resources ?? [], [policiesQuery.data?.resources])

  const isLoading = policiesQuery.isLoading || policiesQuery.isFetching

  return (
    <PolicySelectBase
      id="project-role-policies"
      selected={selected}
      onChange={onChange}
      hasError={hasError}
      policyResources={policyResources}
      isLoading={isLoading}
      fetchAllMatchingPolicies={fetchAllMatchingPolicies}
      clientSideFilterOnly
      toggleTestId="policy-select-toggle"
      onDropdownOpenChange={(open) => {
        setIsOpen(open)
        if (!open) {
          filterValueRef.current = ''
        }
      }}
      onFilterValueChange={handleFilterValueChange}
    />
  )
}
