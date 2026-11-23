import { Content } from '@patternfly/react-core'
import { useQueries } from '@tanstack/react-query'
import { useId, useMemo, type ReactNode } from 'react'

import { integrationsFetchClient } from '../../client'
import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

import type { KafkaGroupConflict } from './node-forms/kafkaPublishedGroups'

type Props = Readonly<{
  conflicts?: KafkaGroupConflict[]
  isPending: boolean
  onConfirm: () => void
  onCancel: () => void
}>

function useIntegrationNames(conflicts: readonly KafkaGroupConflict[] | undefined) {
  const integrationIds = useMemo(
    () => [...new Set(conflicts?.map((conflict) => conflict.source.integration_id) ?? [])],
    [conflicts]
  )
  return useQueries({
    queries: integrationIds.map((integrationId) => ({
      queryKey: ['get', '/integrations/{integration_id}', { integrationId, scope: 'kafka-group-conflict' }],
      queryFn: async () => {
        const { data, error } = await integrationsFetchClient.GET('/integrations/{integration_id}', {
          params: { path: { integration_id: integrationId } },
        })
        // A missing name must not block confirmation; the topic still identifies the source.
        if (error || !data?.name) return null
        return data.name
      },
      retry: false,
      staleTime: 60_000,
    })),
    combine: (results) =>
      new Map(integrationIds.map((integrationId, index) => [integrationId, results[index]?.data ?? undefined])),
  })
}

function sourcePlace(conflict: KafkaGroupConflict, integrationName?: string) {
  return integrationName ? `${integrationName} / ${conflict.source.topic}` : conflict.source.topic
}

function conflictText(conflict: KafkaGroupConflict, integrationName?: string): ReactNode {
  const place = sourcePlace(conflict, integrationName)
  const label = conflict.triggerName ?? place
  const target = conflict.triggerName ? ` for ${place}` : ''
  if (conflict.source.group_id_is_generated) {
    return (
      <>
        {label}: clear <code>{conflict.draftGroup}</code> and keep the automatic group{target}.
      </>
    )
  }
  return (
    <>
      {label}: replace <code>{conflict.draftGroup}</code> with <code>{conflict.source.group_id}</code>
      {target}.
    </>
  )
}

export function KafkaGroupConflictDialog({ conflicts, isPending, onConfirm, onCancel }: Props) {
  const labelId = useId()
  const descriptionId = useId()
  const integrationNames = useIntegrationNames(conflicts)
  return (
    <SynConfirmationDialog
      isOpen={Boolean(conflicts?.length)}
      aria-labelledby={labelId}
      aria-describedby={descriptionId}
      title="Use the published consumer groups?"
      confirmLabel="Use published groups and publish"
      confirmLoading={isPending}
      onConfirm={onConfirm}
      onClose={onCancel}
    >
      <Content component="p">
        These Kafka sources already have fixed consumer groups. Publishing keeps those groups. A different custom id is
        replaced with the published id, and an automatic group stays automatic. Cancel to keep the draft unchanged.
      </Content>
      <Content component="ul">
        {conflicts?.map((conflict) => (
          <Content component="li" key={conflict.triggerId}>
            {conflictText(conflict, integrationNames.get(conflict.source.integration_id) ?? undefined)}
          </Content>
        ))}
      </Content>
    </SynConfirmationDialog>
  )
}
