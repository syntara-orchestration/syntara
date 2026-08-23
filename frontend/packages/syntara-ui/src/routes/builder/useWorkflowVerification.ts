import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useState } from 'react'

import { workflowFetchClient } from '../../client'
import { useAlerts } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { getErrorMessage } from '../../utils/apiErrors'

import type { BuilderAction, ValidationError, ValidationSeverity } from './builderReducer'
import { validateWorkflow } from './utils/validation'
import { formatValidationFindingMessage } from './utils/validation/formatValidationFindingMessage'
import { validateMinimumWorkflow } from './utils/validation/rules/validateMinimumWorkflow'
import { buildWorkflowDefinition } from './utils/workflowDefinitionBuilder'

type ValidationFinding = { message: string; node_id?: string | null; severity?: string; field_path?: string | null }

function lookupNodeName(nodeId: string | null): string | undefined {
  if (!nodeId) return undefined
  const activities = useWorkflowStore.getState().currentWorkflow?.workflow?.activities
  if (!activities) return undefined
  const match = activities.find((a) => a.id === nodeId)
  return match?.name ?? undefined
}

function mapFindings(findings: ValidationFinding[] | undefined): ValidationError[] {
  if (!findings?.length) return []
  return findings.map((f) => {
    const severity: ValidationSeverity = f.severity === 'warning' ? 'warning' : 'error'
    const nodeId = f.node_id ?? null
    const nodeName = lookupNodeName(nodeId)
    return {
      message: formatValidationFindingMessage(f.message, nodeId, nodeName),
      nodeId,
      nodeName,
      severity,
      fieldPath: f.field_path ?? null,
    }
  })
}

function applyValidationState(dispatch: (action: BuilderAction) => void, errors: ValidationError[]): void {
  if (errors.length > 0) {
    dispatch({ type: 'SET_VALIDATION_ERRORS', payload: errors })
    useWorkflowStore.getState().setValidationErrorCount(errors.length)
  } else {
    dispatch({ type: 'CLEAR_VALIDATION_ERRORS' })
    useWorkflowStore.getState().setValidationErrorCount(0)
  }
}

export function extractValidationErrors(err: Record<string, unknown> | undefined): ValidationError[] | null {
  if (!err) return null

  const validationResult = err.validation_result as
    | {
        findings?: ValidationFinding[]
      }
    | undefined

  if (!validationResult) return null

  if (validationResult.findings && Array.isArray(validationResult.findings)) {
    return mapFindings(validationResult.findings)
  }

  return null
}

/**
 * Like extractValidationErrors, but also unwraps openapi-fetch / TanStack mutation
 * wrappers that nest the RFC 9457 body under `cause` or `data`.
 */
export function extractValidationErrorsFromUnknown(error: unknown): ValidationError[] | null {
  if (!error || typeof error !== 'object') return null

  const err = error as Record<string, unknown>
  const direct = extractValidationErrors(err)
  if (direct) return direct

  if (err.cause && typeof err.cause === 'object') {
    const fromCause = extractValidationErrors(err.cause as Record<string, unknown>)
    if (fromCause) return fromCause
  }

  if (err.data && typeof err.data === 'object') {
    return extractValidationErrors(err.data as Record<string, unknown>)
  }

  return null
}

type ValidateResponse = {
  data?: { is_valid?: boolean; findings?: ValidationFinding[] }
  error?: unknown
  response: { ok: boolean }
}

function processValidateResponse(
  { data, error, response }: ValidateResponse,
  dispatch: (action: BuilderAction) => void,
  callbacks: {
    frontendErrors: ValidationError[]
    onValid?: () => void
    silent: boolean
    showSuccess: (opts: { title: string }) => void
    showError: (opts: { title: string; description: string }) => void
  }
): void {
  let backendErrors: ValidationError[] = []

  if (response.ok && data) {
    backendErrors = mapFindings(data.findings)
  } else {
    const err = error as Record<string, unknown> | undefined
    const extracted = extractValidationErrors(err)
    if (extracted) {
      backendErrors = extracted
    } else {
      applyValidationState(dispatch, callbacks.frontendErrors)
      if (!callbacks.silent) {
        callbacks.showError({ title: 'Verification failed', description: getErrorMessage(err) })
      }
      return
    }
  }

  const allIssues = [...callbacks.frontendErrors, ...backendErrors]
  applyValidationState(dispatch, allIssues)

  if (allIssues.length > 0) {
    return
  }

  if (callbacks.onValid) {
    callbacks.onValid()
  } else if (!callbacks.silent) {
    callbacks.showSuccess({ title: 'Workflow verified' })
  }
}

type UseWorkflowVerificationOptions = Readonly<{
  dispatch: (action: BuilderAction) => void
}>

export function useWorkflowVerification({ dispatch }: UseWorkflowVerificationOptions) {
  const { showError, showSuccess } = useAlerts()
  const [isVerifying, setIsVerifying] = useState(false)
  const validationErrorCount = useWorkflowStore((state) => state.validationErrorCount)

  const handleVerify = useCallback(
    (onValid?: () => void, options?: { silent?: boolean }) => {
      const silent = options?.silent ?? false
      const { currentWorkflow, edges, nodePositions } = useWorkflowStore.getState()
      if (!currentWorkflow) {
        dispatch({ type: 'SET_KEBAB_OPEN', payload: false })
        return
      }

      dispatch({ type: 'SET_KEBAB_OPEN', payload: false })

      const { activities } = currentWorkflow.workflow
      const triggers = currentWorkflow.triggers ?? []
      const name = currentWorkflow.name ?? 'workflow'
      const description = currentWorkflow.description ?? ''

      let definition: ReturnType<typeof buildWorkflowDefinition>
      try {
        definition = buildWorkflowDefinition(name, description, activities, triggers, {
          edges,
          nodePositions,
        })
      } catch (err: unknown) {
        dispatch({ type: 'CLEAR_VALIDATION_ERRORS' })
        useWorkflowStore.getState().setValidationErrorCount(0)
        if (!silent) {
          showError({ title: 'Verification failed', description: getErrorMessage(err) })
        }
        return
      }

      dispatch({ type: 'CLEAR_VALIDATION_ERRORS' })

      const frontendResult = validateWorkflow(activities, edges, { triggers })
      const minimumErrors = validateMinimumWorkflow(activities, edges, triggers)
      const nameMap = new Map(activities.map((a) => [a.id, a.name ?? a.id]))
      const allFrontendErrors: ValidationError[] = [...frontendResult.errors, ...minimumErrors].map((e) => ({
        message: e.message,
        nodeId: e.nodeId ?? null,
        nodeName: e.nodeId ? nameMap.get(e.nodeId) : undefined,
        severity: (e.severity ?? 'error') as ValidationSeverity,
      }))

      setIsVerifying(true)
      workflowFetchClient
        .POST('/workflows/validate', {
          body: {
            workflow_definition: definition as unknown as WorkflowAPI.components['schemas']['WorkflowDefinition'],
          },
        })
        .then((resp) => {
          processValidateResponse(resp as ValidateResponse, dispatch, {
            frontendErrors: allFrontendErrors,
            onValid,
            silent,
            showSuccess,
            showError,
          })
        })
        .catch((err: unknown) => {
          applyValidationState(dispatch, allFrontendErrors)
          if (!silent) {
            showError({ title: 'Verification failed', description: getErrorMessage(err) })
          }
        })
        .finally(() => setIsVerifying(false))
    },
    [dispatch, showError, showSuccess]
  )

  const handleVerifySilent = useCallback(
    (onValid?: () => void) => handleVerify(onValid, { silent: true }),
    [handleVerify]
  )

  return { handleVerify, handleVerifySilent, isVerifying, validationErrorCount }
}
