import { TriggerTypeEnum, type Activity, type WorkflowAPI } from '@syntara/contracts'

import { parseJsonSchema } from '../../../utils/jsonSafeParse'

import { triggerFormSchema, type TriggerFormData } from './triggerFormSchema'

export type KafkaSubscribeParameters = WorkflowAPI.components['schemas']['KafkaSubscribeParameters']

export function kafkaSubscribeParameters(data: TriggerFormData): KafkaSubscribeParameters {
  const validated = triggerFormSchema.parse({ ...data, triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE })
  const inputSchema = parseJsonSchema(validated.inputSchema)
  return {
    integration_id: validated.integrationId ?? '',
    credential_id: validated.runtimeCredentialId ?? '',
    topic: validated.topic ?? '',
    ...(inputSchema && { input_schema: inputSchema }),
  }
}

/** Shared create/edit mapping so reopening a trigger preserves optional omissions. */
export function buildKafkaSubscribeTrigger(id: string, name: string, data: TriggerFormData): Activity {
  return {
    id,
    name,
    type: TriggerTypeEnum.EVENT_SUBSCRIBE,
    parameters: kafkaSubscribeParameters(data),
  }
}

export function kafkaSubscribeFormDefaults(trigger: Activity): TriggerFormData {
  const parameters = trigger.parameters
  const inputSchema = parameters?.input_schema
  return {
    name: trigger.name,
    triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE,
    integrationId: typeof parameters?.integration_id === 'string' ? parameters.integration_id : undefined,
    runtimeCredentialId: typeof parameters?.credential_id === 'string' ? parameters.credential_id : undefined,
    topic: typeof parameters?.topic === 'string' ? parameters.topic : undefined,
    inputSchema: inputSchema && typeof inputSchema === 'object' ? JSON.stringify(inputSchema, null, 2) : undefined,
  }
}
