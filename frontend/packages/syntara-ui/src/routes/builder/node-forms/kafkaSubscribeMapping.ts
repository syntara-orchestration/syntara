import { TriggerTypeEnum, type Activity, type WorkflowAPI } from '@syntara/contracts'

import { parseJsonSchema } from '../../../utils/jsonSafeParse'

import { triggerFormSchema, type TriggerFormData } from './triggerFormSchema'

export type KafkaSubscribeParameters = WorkflowAPI.components['schemas']['KafkaSubscribeParameters']

/** Match Python str.strip(): Unicode White_Space plus the four ASCII information separators. */
export function hasKafkaFilterExpression(expression: string): boolean {
  return Array.from(expression).some((character) => {
    const code = character.codePointAt(0) ?? 0
    return !/\p{White_Space}/u.test(character) && !(code >= 28 && code <= 31)
  })
}

function kafkaFilter(expression = ''): KafkaSubscribeParameters['filter'] {
  return hasKafkaFilterExpression(expression) ? { expression } : null
}

export function kafkaSubscribeParameters(data: TriggerFormData): KafkaSubscribeParameters {
  const validated = triggerFormSchema.parse({ ...data, triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE })
  if (!validated.integrationId || !validated.runtimeCredentialId || !validated.topic) {
    throw new Error('Select an Integration, runtime credential, and exact topic')
  }
  const inputSchema = parseJsonSchema(validated.inputSchema)
  return {
    integration_id: validated.integrationId ?? '',
    credential_id: validated.runtimeCredentialId ?? '',
    topic: validated.topic ?? '',
    filter: kafkaFilter(validated.filterExpression),
    ...(inputSchema && { input_schema: inputSchema }),
  }
}

/** Drafts omit missing fields; execution and preflight still require the complete contract. */
function kafkaSubscribeDraftParameters(data: TriggerFormData): Partial<KafkaSubscribeParameters> {
  const validated = triggerFormSchema.parse({ ...data, triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE })
  const inputSchema = parseJsonSchema(validated.inputSchema)
  return {
    ...(validated.integrationId && { integration_id: validated.integrationId }),
    ...(validated.runtimeCredentialId && { credential_id: validated.runtimeCredentialId }),
    ...(validated.topic && { topic: validated.topic }),
    filter: kafkaFilter(validated.filterExpression),
    ...(inputSchema && { input_schema: inputSchema }),
  }
}

/** Shared create/edit mapping so reopening a trigger preserves optional omissions. */
export function buildKafkaSubscribeTrigger(id: string, name: string, data: TriggerFormData): Activity {
  return {
    id,
    name,
    type: TriggerTypeEnum.EVENT_SUBSCRIBE,
    parameters: kafkaSubscribeDraftParameters(data),
  }
}

export function kafkaSubscribeFormDefaults(trigger: Activity): TriggerFormData {
  const parameters = trigger.parameters
  const inputSchema = parameters?.input_schema
  const filter = parameters?.filter
  return {
    name: trigger.name,
    triggerType: TriggerTypeEnum.EVENT_SUBSCRIBE,
    integrationId: typeof parameters?.integration_id === 'string' ? parameters.integration_id : undefined,
    runtimeCredentialId: typeof parameters?.credential_id === 'string' ? parameters.credential_id : undefined,
    topic: typeof parameters?.topic === 'string' ? parameters.topic : undefined,
    filterExpression:
      filter && typeof filter === 'object' && 'expression' in filter && typeof filter.expression === 'string'
        ? filter.expression
        : undefined,
    inputSchema: inputSchema && typeof inputSchema === 'object' ? JSON.stringify(inputSchema, null, 2) : undefined,
  }
}
