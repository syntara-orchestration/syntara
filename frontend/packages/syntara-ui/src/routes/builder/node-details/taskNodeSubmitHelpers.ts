import { ExecutorTypeEnum, type Activity, type TaskActivity } from '@syntara/contracts'

import { generateUUID } from '../../../utils/generateUUID'
import { PROTOTYPE_POLLUTION_KEYS, safeJSONReviver } from '../../../utils/jsonSafeParse'
import { parseJsonEnvironment } from '../../../utils/parseJsonEnvironment'
import type { ActionFormData as RegistryActionFormData } from '../hooks/useNodeCreation'

export { safeJSONReviver }

/**
 * Convert key-value entries from the form into a flat headers object.
 * Skips entries with empty keys and prototype pollution keys.
 */
function headersEntriesToRecord(
  entries: Array<{ key: string; value: string }> | undefined
): Record<string, string> | undefined {
  if (!entries?.length) return undefined

  const result: Record<string, string> = {}
  for (const { key, value } of entries) {
    const trimmedKey = key.trim()
    if (trimmedKey && !PROTOTYPE_POLLUTION_KEYS.has(trimmedKey)) result[trimmedKey] = value
  }
  return Object.keys(result).length > 0 ? result : undefined
}

export function buildRegistryActionInitialData(
  executor: string,
  parameters: Record<string, unknown>,
  taskData: TaskActivity
): Partial<RegistryActionFormData> {
  return {
    name: taskData.name,
    executor: executor === ExecutorTypeEnum.SCRIPT ? ExecutorTypeEnum.SCRIPT : ExecutorTypeEnum.HTTP_REQUEST,
    language: executor === ExecutorTypeEnum.SCRIPT ? (parameters.language as string | undefined) : undefined,
    code: executor === ExecutorTypeEnum.SCRIPT ? (parameters.code as string | undefined) : undefined,
    method:
      executor === ExecutorTypeEnum.HTTP_REQUEST
        ? (parameters.method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | undefined)
        : undefined,
    url: executor === ExecutorTypeEnum.HTTP_REQUEST ? (parameters.url as string | undefined) : undefined,
    headers:
      executor === ExecutorTypeEnum.HTTP_REQUEST && parameters.headers
        ? Object.entries(parameters.headers as Record<string, string>).map(([key, value]) => ({
            id: generateUUID(),
            key,
            value: String(value),
          }))
        : undefined,
    body: (() => {
      if (executor !== ExecutorTypeEnum.HTTP_REQUEST || !parameters.body) {
        return undefined
      }
      return typeof parameters.body === 'string' ? parameters.body : JSON.stringify(parameters.body, null, 2)
    })(),
    credential_id: (parameters as { credential_id?: string }).credential_id ?? undefined,
    parameters:
      executor === ExecutorTypeEnum.SCRIPT && parameters.environment
        ? JSON.stringify(parameters.environment, null, 2)
        : undefined,
  }
}

export function buildRegistryActivityUpdate(taskData: TaskActivity, data: RegistryActionFormData): Activity {
  const apiHeaders = data.executor === ExecutorTypeEnum.HTTP_REQUEST ? headersEntriesToRecord(data.headers) : undefined

  const scriptEnv = data.executor === ExecutorTypeEnum.SCRIPT ? parseJsonEnvironment(data.parameters) : undefined

  return {
    ...taskData,
    name: data.name,
    type: data.executor === ExecutorTypeEnum.SCRIPT ? ExecutorTypeEnum.SCRIPT : ExecutorTypeEnum.HTTP_REQUEST,
    parameters:
      data.executor === ExecutorTypeEnum.SCRIPT
        ? {
            language: data.language ?? 'python',
            code: data.code!,
            ...(data.credential_id && { credential_id: data.credential_id }),
            ...(scriptEnv && { environment: scriptEnv }),
          }
        : {
            method: data.method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
            url: data.url!,
            ...(apiHeaders && { headers: apiHeaders }),
            ...(data.body && {
              body: parseHttpBodyField(data.body),
            }),
            ...(data.credential_id && { credential_id: data.credential_id }),
          },
  } as Activity
}

function parseHttpBodyField(body: string): unknown {
  try {
    return JSON.parse(body, safeJSONReviver) as unknown
  } catch {
    return body
  }
}
