import { ExecutorTypeEnum, type Activity, type TaskActivity } from '@syntara/contracts'

import { generateUUID } from '../../../utils/generateUUID'
import { PROTOTYPE_POLLUTION_KEYS, safeJSONReviver } from '../../../utils/jsonSafeParse'
import { parseJsonEnvironment } from '../../../utils/parseJsonEnvironment'
import type { ActionFormData as RegistryActionFormData } from '../stepFormTypes'
import { buildScriptExecutionProfile, parseScriptExecutionFormFields } from '../utils/scriptExecutionProfile'

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

function serializeBody(body: unknown): string {
  if (typeof body === 'string') return body
  return JSON.stringify(body, null, 2)
}

/** Hydrate ActionStepForm initial data from a stored script/HTTP activity. */
export function buildRegistryActionInitialData(
  executor: string,
  parameters: Record<string, unknown>,
  taskData: TaskActivity
): Partial<RegistryActionFormData> {
  const isScript = executor === ExecutorTypeEnum.SCRIPT
  const isHTTP = executor === ExecutorTypeEnum.HTTP_REQUEST
  const executionFields = isScript ? parseScriptExecutionFormFields(parameters) : undefined
  const credentialId =
    (parameters as { credentialId?: string; credential_id?: string }).credentialId ??
    (parameters as { credentialId?: string; credential_id?: string }).credential_id

  return {
    name: taskData.name,
    executor: isScript ? ExecutorTypeEnum.SCRIPT : ExecutorTypeEnum.HTTP_REQUEST,
    language: isScript ? (parameters.language as string | undefined) : undefined,
    code: isScript ? (parameters.code as string | undefined) : undefined,
    method: isHTTP ? (parameters.method as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | undefined) : undefined,
    url: isHTTP ? (parameters.url as string | undefined) : undefined,
    headers:
      isHTTP && parameters.headers
        ? Object.entries(parameters.headers as Record<string, string>).map(([key, value]) => ({
            id: generateUUID(),
            key,
            value: String(value),
          }))
        : undefined,
    body: isHTTP && parameters.body ? serializeBody(parameters.body) : undefined,
    credential_id: credentialId ?? undefined,
    parameters: isScript && parameters.environment ? JSON.stringify(parameters.environment, null, 2) : undefined,
    affinity: executionFields?.affinity,
    execution_target_id: executionFields?.execution_target_id,
    settings: taskData.settings,
  }
}

/** Build the updated activity for a script/HTTP ActionStepForm submit. */
export function buildRegistryActivityUpdate(taskData: TaskActivity, data: RegistryActionFormData): Activity {
  const apiHeaders = data.executor === ExecutorTypeEnum.HTTP_REQUEST ? headersEntriesToRecord(data.headers) : undefined

  const scriptEnv = data.executor === ExecutorTypeEnum.SCRIPT ? parseJsonEnvironment(data.parameters) : undefined
  const executionProfile =
    data.executor === ExecutorTypeEnum.SCRIPT
      ? buildScriptExecutionProfile(data.affinity, data.execution_target_id)
      : undefined

  return {
    ...taskData,
    name: data.name,
    type: data.executor === ExecutorTypeEnum.SCRIPT ? ExecutorTypeEnum.SCRIPT : ExecutorTypeEnum.HTTP_REQUEST,
    parameters:
      data.executor === ExecutorTypeEnum.SCRIPT
        ? {
            language: data.language ?? 'python',
            code: data.code ?? '',
            ...(data.credential_id && { credential_id: data.credential_id }),
            ...(scriptEnv && { environment: scriptEnv }),
            ...(executionProfile && { execution_profile: executionProfile }),
          }
        : {
            method: data.method,
            url: data.url ?? '',
            ...(apiHeaders && { headers: apiHeaders }),
            ...(data.body && {
              body: parseHttpBodyField(data.body),
            }),
            ...(data.credential_id && { credential_id: data.credential_id }),
          },
    settings: data.settings,
  }
}

function parseHttpBodyField(body: string): unknown {
  try {
    return JSON.parse(body, safeJSONReviver) as unknown
  } catch {
    return body
  }
}
