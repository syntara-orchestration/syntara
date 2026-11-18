import { TriggerTypeEnum } from '@syntara/contracts'
import { useMutation } from '@tanstack/react-query'
import { useCallback, useRef } from 'react'

import { workflowFetchClient } from '../../../client'
import { useDialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'
import { kafkaSourceRevision, readKafkaPublication, reconcileKafkaGroups } from '../node-forms/kafkaPublishedGroups'

export type PublishCallOptions = { expectedVersionOverride?: number; versionOverride?: number }
export type PreparedPublishOptions = PublishCallOptions & { workflowDefinition?: Record<string, unknown> }
type Request = {
  name?: string
  description?: string
  onSettled?: () => void
  options?: PublishCallOptions
  definition?: Record<string, unknown>
}

async function prepareGroups(workflowId: string, version: number, request: Request) {
  const publication = await readKafkaPublication(workflowId)
  let definition = request.definition
  if (!definition) {
    if (publication.version.version === version) {
      definition = publication.version.workflow_definition
    } else {
      const { data, error } = await workflowFetchClient.GET('/workflows/{workflow_id}/versions/{version}', {
        params: { path: { workflow_id: workflowId, version } },
      })
      if (error) throw new Error(getErrorMessage(error), { cause: error })
      if (!data) throw new Error('The workflow version is unavailable')
      definition = data.workflow_definition
    }
  }
  const sources = publication.kafka_subscription_sources ?? []
  const result = reconcileKafkaGroups(definition, sources)
  return {
    request,
    conflicts: result.conflicts,
    revision: kafkaSourceRevision(sources),
    definition: result.changed || request.definition ? result.definition : undefined,
  }
}

type Plan = Awaited<ReturnType<typeof prepareGroups>>
type Options = {
  workflowId: string | null
  currentVersion?: number
  getDefinition: () => Record<string, unknown> | undefined
  submit: (name?: string, description?: string, onSettled?: () => void, options?: PreparedPublishOptions) => void
}

export function useKafkaPublishGroups({ workflowId, currentVersion, getDefinition, submit }: Options) {
  const dialog = useDialogState<Plan>()
  const requestEpoch = useRef(0)
  const { showError } = useAlerts()
  const preparation = useMutation({
    mutationFn: ({ version, request }: { version: number; request: Request }) => {
      if (!workflowId) throw new Error('Workflow ID is required')
      return prepareGroups(workflowId, version, request)
    },
  })
  const { mutateAsync, reset } = preparation
  const { open, close, item: data } = dialog

  const checkAndPublish = useCallback(
    async (request: Request, acceptedRevision?: string) => {
      const version = request.options?.versionOverride ?? currentVersion
      if (!workflowId || version == null) return
      const epoch = ++requestEpoch.current
      try {
        const plan = await mutateAsync({ version, request })
        if (epoch !== requestEpoch.current) return
        if (plan.conflicts.length && plan.revision !== acceptedRevision) {
          request.onSettled?.()
          open({ ...plan, request: { ...request, onSettled: undefined } })
          return
        }
        if (acceptedRevision !== undefined && plan.revision !== acceptedRevision) {
          close()
          throw new Error('The published Kafka source changed. Review the workflow and publish again.')
        }
        close()
        submit(request.name, request.description, request.onSettled, {
          ...request.options,
          workflowDefinition: plan.definition,
        })
      } catch (error) {
        if (epoch !== requestEpoch.current) return
        showError({ title: 'Unable to prepare Kafka consumer groups', description: getErrorMessage(error) })
        request.onSettled?.()
      }
    },
    [workflowId, currentVersion, mutateAsync, open, close, submit, showError]
  )

  const publish = useCallback(
    (name?: string, description?: string, onSettled?: () => void, options?: PublishCallOptions) => {
      const definition = getDefinition()
      const triggers: unknown = definition?.triggers ?? useWorkflowStore.getState().currentWorkflow?.triggers
      const hasKafka =
        Array.isArray(triggers) &&
        triggers.some(
          (trigger: unknown) =>
            typeof trigger === 'object' &&
            trigger !== null &&
            'type' in trigger &&
            trigger.type === TriggerTypeEnum.EVENT_SUBSCRIBE
        )
      if (!hasKafka && options?.versionOverride === undefined) {
        submit(name, description, onSettled, { ...options, workflowDefinition: definition })
        return
      }
      detachPromise(checkAndPublish({ name, description, onSettled, options, definition }))
    },
    [getDefinition, submit, checkAndPublish]
  )

  const confirmGroups = useCallback(() => {
    if (data) detachPromise(checkAndPublish(data.request, data.revision))
  }, [data, checkAndPublish])
  const cancelGroups = useCallback(() => {
    requestEpoch.current++
    reset()
    close()
  }, [reset, close])

  return {
    publish,
    isCheckingGroups: preparation.isPending,
    groupConflicts: dialog.isOpen ? data?.conflicts : undefined,
    confirmGroups,
    cancelGroups,
  }
}
