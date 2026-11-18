import { ScheduleTypeEnum, TriggerTypeEnum, WEBHOOK_TRIGGER_TYPES } from '@syntara/contracts'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { ZodType } from 'zod'

import { kafkaPublicationQueryKey, matchingKafkaSource, readKafkaPublication } from './kafkaPublishedGroups'
import { normalizeWebhookPath, type TriggerFormData } from './triggerFormSchema'

function submitData(data: TriggerFormData): TriggerFormData {
  const isManual = data.triggerType === TriggerTypeEnum.MANUAL_TRIGGER
  const isKafka = data.triggerType === TriggerTypeEnum.EVENT_SUBSCRIBE
  const isScheduled = data.triggerType === TriggerTypeEnum.SCHEDULED
  const isWebhookStyle = WEBHOOK_TRIGGER_TYPES.has(data.triggerType)

  return {
    name: data.name,
    triggerType: data.triggerType,
    inputSchema: isManual || isWebhookStyle || isKafka ? data.inputSchema : undefined,
    scheduleType: isScheduled ? data.scheduleType : undefined,
    interval: isScheduled && data.scheduleType === ScheduleTypeEnum.INTERVAL ? data.interval : undefined,
    cron: isScheduled && data.scheduleType === ScheduleTypeEnum.CRON ? data.cron : undefined,
    timezone: isScheduled ? data.timezone : undefined,
    missedSchedulePolicy: isScheduled ? data.missedSchedulePolicy : undefined,
    webhookPath: isWebhookStyle ? normalizeWebhookPath(data.webhookPath ?? '') : undefined,
    integrationId: isKafka ? data.integrationId : undefined,
    runtimeCredentialId: isKafka ? data.runtimeCredentialId : undefined,
    topic: isKafka ? data.topic : undefined,
    filterExpression: isKafka ? data.filterExpression : undefined,
    ...(isKafka && { kafkaStart: data.kafkaStart, kafkaGroupId: data.kafkaGroupId }),
    authorizedServiceAccountIds: isWebhookStyle ? data.authorizedServiceAccountIds : undefined,
  }
}

type Options = Readonly<{
  schema: ZodType<TriggerFormData>
  workflowId?: string | null
  triggerId?: string
  onSubmit: (data: TriggerFormData) => void
}>

export function useTriggerFormSubmit({ schema, workflowId, triggerId, onSubmit }: Options) {
  const queryClient = useQueryClient()
  const groupUpdate = useMutation({
    mutationFn: async (data: TriggerFormData) => {
      if (data.triggerType !== TriggerTypeEnum.EVENT_SUBSCRIBE || !workflowId || !triggerId) return { data }
      const publication = await readKafkaPublication(workflowId)
      const source = matchingKafkaSource(
        publication.kafka_subscription_sources ?? [],
        triggerId,
        data.integrationId,
        data.topic
      )
      return { data: source ? { ...data, kafkaGroupId: source.group_id } : data, publication }
    },
  })

  const submit = async (submitted: TriggerFormData) => {
    if (groupUpdate.isPending) return false
    let succeeded = false
    try {
      await groupUpdate.mutateAsync(submitted, {
        onSuccess: ({ data, publication }) => {
          if (publication) queryClient.setQueryData(kafkaPublicationQueryKey(workflowId), publication)
          const result = schema.safeParse(data)
          if (!result.success) return
          onSubmit(submitData(result.data))
          succeeded = true
        },
      })
    } catch {
      return false
    }
    return succeeded
  }
  return { submit, isPending: groupUpdate.isPending, isError: groupUpdate.isError, error: groupUpdate.error }
}
