import { useMemo } from 'react'

import { credentialsClient } from '../../../../client'

import { getTypeInputs } from './credentialFormUtils'

export function useCredentialFormModalQueries(compatibleTypeNames: string[] | undefined, selectedTypeId: string) {
  const typesQuery = credentialsClient.useQuery('get', '/credential_types')
  const allTypes = useMemo(() => typesQuery.data?.resources ?? [], [typesQuery.data])
  const types = useMemo(() => {
    if (!compatibleTypeNames?.length) return allTypes
    return allTypes.filter((t) => compatibleTypeNames.includes(t.name))
  }, [allTypes, compatibleTypeNames])

  const selectedType = useMemo(() => types.find((t) => t.id === selectedTypeId), [types, selectedTypeId])
  const typeInputs = useMemo(() => (selectedType ? getTypeInputs(selectedType) : null), [selectedType])

  return { typesQuery, allTypes, types, selectedType, typeInputs }
}
