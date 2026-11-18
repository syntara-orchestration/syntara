import { useQuery } from '@tanstack/react-query'

import { kafkaPublicationQueryKey, readKafkaPublication } from './kafkaPublishedGroups'

/** Read the current projection, including while unpublished, independently of version-history length. */
export function useKafkaPublishedSource(workflowId?: string | null, triggerId?: string) {
  const enabled = Boolean(workflowId && triggerId)
  const query = useQuery({
    queryKey: kafkaPublicationQueryKey(workflowId),
    enabled,
    queryFn: () => {
      if (!workflowId) throw new Error('Workflow ID is required')
      return readKafkaPublication(workflowId)
    },
  })
  const isChecking = enabled && (query.isPending || query.isFetching)
  return {
    // Cached data must not lock a replacement source while a fresh projection is being fetched.
    source:
      isChecking || query.isError
        ? undefined
        : query.data?.kafka_subscription_sources?.find((source) => source.trigger_node_id === triggerId),
    isError: query.isError,
    isSuccess: query.isSuccess,
    error: query.error,
    refetch: query.refetch,
    isChecking,
  }
}
