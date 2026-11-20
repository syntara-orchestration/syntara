import { ActivityTypeEnum, TriggerTypeEnum } from '@syntara/contracts'

import { orderValuesByFieldOrder } from '../../../forms'
import { buildTriggerNodeId } from '../../../utils/triggerNodeIds'

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }

  const prototype: unknown = Object.getPrototypeOf(value)
  return prototype === Object.prototype || prototype === null
}

/** Read field names without validating unrelated form-field properties. */
export function formFieldOrderFromParameters(parameters: unknown): string[] | undefined {
  if (!isPlainObject(parameters) || !isPlainObject(parameters.form_definition)) {
    return undefined
  }

  const fields = parameters.form_definition.fields
  if (!Array.isArray(fields) || fields.length === 0) {
    return undefined
  }

  const valueNames: string[] = []
  for (const field of fields) {
    if (!isPlainObject(field) || typeof field.value_name !== 'string' || field.value_name.length === 0) {
      return undefined
    }
    valueNames.push(field.value_name)
  }

  return valueNames
}

function addFormOrder(result: Map<string, string[]>, node: unknown, expectedType: string, nodeId?: string): void {
  if (!isPlainObject(node) || node.type !== expectedType) {
    return
  }

  const order = formFieldOrderFromParameters(node.parameters)
  if (order && nodeId) {
    result.set(nodeId, order)
  }
}

/** Build ordering metadata for form activities and form triggers in a v2 definition. */
export function buildFormFieldOrderMap(workflowDefinition: unknown): Map<string, string[]> {
  const result = new Map<string, string[]>()
  if (!isPlainObject(workflowDefinition)) {
    return result
  }

  if (Array.isArray(workflowDefinition.nodes)) {
    for (const node of workflowDefinition.nodes) {
      if (isPlainObject(node) && typeof node.id === 'string') {
        addFormOrder(result, node, ActivityTypeEnum.FORM_PROMPT, node.id)
      }
    }
  }

  if (Array.isArray(workflowDefinition.triggers)) {
    workflowDefinition.triggers.forEach((trigger, index) => {
      if (!isPlainObject(trigger) || trigger.type !== TriggerTypeEnum.FORM_TRIGGER) {
        return
      }

      const order = formFieldOrderFromParameters(trigger.parameters)
      if (!order) {
        return
      }

      if (typeof trigger.id === 'string') {
        result.set(trigger.id, order)
      }
      result.set(buildTriggerNodeId(index), order)
    })
  }

  return result
}

/** Reorder only the submission values carried by form activity data. */
export function orderFormActivityData<T extends Record<string, unknown> | null>(
  data: T,
  nodeType: string | undefined,
  order: readonly string[] | undefined,
  direction: 'input' | 'output'
): T
export function orderFormActivityData(
  data: unknown,
  nodeType: string | undefined,
  order: readonly string[] | undefined,
  direction: 'input' | 'output'
): unknown
export function orderFormActivityData(
  data: unknown,
  nodeType: string | undefined,
  order: readonly string[] | undefined,
  direction: 'input' | 'output'
): unknown {
  if (!isPlainObject(data) || !order || order.length === 0) {
    return data
  }

  if (nodeType === TriggerTypeEnum.FORM_TRIGGER) {
    if (direction === 'input') {
      return orderValuesByFieldOrder(data, order)
    }
    if (!isPlainObject(data.response_data)) {
      return data
    }

    const orderedTriggerResponseData = orderValuesByFieldOrder(data.response_data, order)
    return orderedTriggerResponseData === data.response_data
      ? data
      : { ...data, response_data: orderedTriggerResponseData }
  }

  if (nodeType !== ActivityTypeEnum.FORM_PROMPT || direction !== 'output' || !isPlainObject(data.response_data)) {
    return data
  }

  const orderedResponseData = orderValuesByFieldOrder(data.response_data, order)
  return orderedResponseData === data.response_data ? data : { ...data, response_data: orderedResponseData }
}
