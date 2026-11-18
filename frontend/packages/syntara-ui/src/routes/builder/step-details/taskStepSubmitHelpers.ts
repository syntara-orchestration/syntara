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

export function buildRegistryActionInitialData(
  executor: string,
  parameters: Record<string, unknown>,
  taskData: TaskActivity
): Partial<RegistryActionFormData> {
  let formExecutor: RegistryActionFormData['executor'] = ExecutorTypeEnum.HTTP_REQUEST
  if (executor === ExecutorTypeEnum.SCRIPT_PYTHON) {
    formExecutor = ExecutorTypeEnum.SCRIPT_PYTHON
  } else if (executor === ExecutorTypeEnum.SCRIPT_BASH) {
    formExecutor = ExecutorTypeEnum.SCRIPT_BASH
  }
  const isScript = executor === ExecutorTypeEnum.SCRIPT_PYTHON || executor === ExecutorTypeEnum.SCRIPT_BASH
  const executionFields = isScript ? parseScriptExecutionFormFields(parameters) : undefined

  return {
    name: taskData.name,
    executor: formExecutor,
    code:
      executor === ExecutorTypeEnum.SCRIPT_PYTHON || executor === ExecutorTypeEnum.SCRIPT_BASH
        ? (parameters.code as string | undefined)
        : undefined,
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
    parameters: isScript && parameters.environment ? JSON.stringify(parameters.environment, null, 2) : undefined,
    ...executionFields,
    settings: taskData.settings,
  }
}

export function buildRegistryActivityUpdate(taskData: TaskActivity, data: RegistryActionFormData): Activity {
  const apiHeaders = data.executor === ExecutorTypeEnum.HTTP_REQUEST ? headersEntriesToRecord(data.headers) : undefined

  const isPythonScript = data.executor === ExecutorTypeEnum.SCRIPT_PYTHON
  const isBashScript = data.executor === ExecutorTypeEnum.SCRIPT_BASH
  const isScript = isPythonScript || isBashScript
  const scriptEnv = isScript ? parseJsonEnvironment(data.parameters) : undefined
  const existingScriptConfig =
    taskData.type === ExecutorTypeEnum.SCRIPT_PYTHON || taskData.type === ExecutorTypeEnum.SCRIPT_BASH
      ? taskData.parameters
      : undefined
  const scriptParameters = { ...existingScriptConfig, code: data.code ?? '' }
  const executionProfile = isScript ? buildScriptExecutionProfile(data.affinity, data.execution_target_id) : undefined
  if (scriptEnv) {
    scriptParameters.environment = scriptEnv
  } else {
    delete scriptParameters.environment
  }
  if (executionProfile) {
    scriptParameters.execution_profile = executionProfile
  } else {
    delete scriptParameters.execution_profile
  }

  return {
    ...taskData,
    name: data.name,
    type: data.executor,
    settings: data.settings,
    parameters: isScript
      ? scriptParameters
      : {
          method: data.method,
          url: data.url ?? '',
          ...(apiHeaders && { headers: apiHeaders }),
          ...(data.body && {
            body: parseHttpBodyField(data.body),
          }),
          ...(data.credential_id && { credential_id: data.credential_id }),
        },
  }
}

function parseHttpBodyField(body: string): unknown {
  try {
    return JSON.parse(body, safeJSONReviver) as unknown
  } catch {
    return body
  }
}
