import { credentialsClient } from '../../../client'
import { useAllCredentials } from '../../builder/components/useAllCredentials'

/** Read the selected credential type from the same records the selector uses. */
export function useKafkaCredentialType(credentialId?: string | null, projectId?: string): string | undefined {
  const enabled = Boolean(credentialId)
  const { credentials, isLoading } = useAllCredentials({ projectId, enabled })
  const selected = credentials.find((item) => item.id === credentialId)
  const { data: storedCredential } = credentialsClient.useQuery(
    'get',
    '/credentials/{credential_id}',
    { params: { path: { credential_id: credentialId ?? '' } } },
    { enabled: enabled && !isLoading && !selected }
  )
  const { data: types } = credentialsClient.useQuery('get', '/credential_types', undefined, { enabled })
  const typeId = (selected ?? storedCredential)?.credential_type_id
  return types?.resources.find((type) => type.id === typeId)?.name
}
