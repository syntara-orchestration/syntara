import type { ExecutionPlaneAPI } from '@syntara/contracts'
import type { FieldNamesMarkedBoolean } from 'react-hook-form'
import { z } from 'zod'

import { getNodeSelectors } from './getNodeSelectors'

/** Kubernetes DNS label (namespace). Matches Execution Plane `KubernetesPlacement.namespace`. */
const NAMESPACE_PATTERN = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/

/**
 * Kubernetes label name (optional DNS subdomain prefix + `/` + name).
 * Mirrors `execution_plane_client.commands.targets._label_key`.
 */
const LABEL_NAME_PATTERN = /^[A-Za-z0-9]([A-Za-z0-9_.-]*[A-Za-z0-9])?$/
const DNS_LABEL_PATTERN = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/
const LABEL_LIMIT = 63
const DOMAIN_LIMIT = 253

export function isKubernetesLabelKey(value: string): boolean {
  const slashIndex = value.indexOf('/')
  if (slashIndex === -1) {
    return value.length <= LABEL_LIMIT && LABEL_NAME_PATTERN.test(value)
  }
  const prefix = value.slice(0, slashIndex)
  const name = value.slice(slashIndex + 1)
  if (
    !prefix ||
    prefix.length > DOMAIN_LIMIT ||
    prefix.split('.').some((part) => part.length > LABEL_LIMIT || !DNS_LABEL_PATTERN.test(part))
  ) {
    return false
  }
  return name.length <= LABEL_LIMIT && LABEL_NAME_PATTERN.test(name)
}

export function isKubernetesLabelValue(value: string): boolean {
  return value.length <= LABEL_LIMIT && (value === '' || LABEL_NAME_PATTERN.test(value))
}

const nodeSelectorPairSchema = z
  .object({
    key: z.string(),
    value: z.string(),
  })
  .superRefine((pair, ctx) => {
    const key = pair.key.trim()
    const value = pair.value.trim()
    if (!key && !value) {
      return
    }
    if (!key) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Key is required', path: ['key'] })
      return
    }
    if (!isKubernetesLabelKey(key)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Invalid Kubernetes label key', path: ['key'] })
    }
    if (!isKubernetesLabelValue(value)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'Invalid Kubernetes label value', path: ['value'] })
    }
  })

export const executionTargetFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Execution target name is required')
    .max(255, 'Execution target name must be 255 characters or fewer'),
  namespace: z
    .string()
    .trim()
    .min(1, 'Execution namespace is required')
    .max(63, 'Execution namespace must be 63 characters or fewer')
    .regex(NAMESPACE_PATTERN, 'Invalid namespace format'),
  nodeSelectors: z.array(nodeSelectorPairSchema),
})

export type ExecutionTargetFormData = z.infer<typeof executionTargetFormSchema>

type ExecutionTargetCreate = ExecutionPlaneAPI.components['schemas']['ExecutionTargetCreate']
type ExecutionTargetRead = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']
type ExecutionTargetUpdate = ExecutionPlaneAPI.components['schemas']['ExecutionTargetUpdate']
type KubernetesTargetPlacement = ExecutionPlaneAPI.components['schemas']['KubernetesTargetPlacement']

export type ExecutionTargetDirtyFields = Partial<Readonly<FieldNamesMarkedBoolean<ExecutionTargetFormData>>>

/** Parse `key=value` node selector strings into form rows. */
export function parseNodeSelectorPairs(selectors: readonly string[]): ExecutionTargetFormData['nodeSelectors'] {
  const pairs = selectors
    .map((selector) => {
      const eqIndex = selector.indexOf('=')
      if (eqIndex === -1) {
        return { key: selector.trim(), value: '' }
      }
      return {
        key: selector.slice(0, eqIndex).trim(),
        value: selector.slice(eqIndex + 1).trim(),
      }
    })
    .filter((pair) => pair.key.length > 0)

  return pairs.length > 0 ? pairs : [{ key: '', value: '' }]
}

function buildKubernetesPlacement(
  data: ExecutionTargetFormData,
  options?: { tolerations?: string[] }
): KubernetesTargetPlacement {
  const node_selectors = data.nodeSelectors
    .map((pair) => ({ key: pair.key.trim(), value: pair.value.trim() }))
    .filter((pair) => pair.key.length > 0)
    .map((pair) => `${pair.key}=${pair.value}`)

  return {
    type: 'kubernetes',
    namespace: data.namespace.trim(),
    ...(node_selectors.length > 0 ? { node_selectors } : {}),
    // Form does not edit tolerations; re-send existing ones when rebuilding placement
    // so a namespace/selector PATCH does not wipe them on the server.
    ...(options?.tolerations !== undefined ? { tolerations: options.tolerations } : {}),
  }
}

function getExistingKubernetesTolerations(target: ExecutionTargetRead | undefined): string[] | undefined {
  const placement = target?.placement
  return placement?.type === 'kubernetes' ? placement.tolerations : undefined
}

/** True when react-hook-form marks a field (or nested field-array entry) dirty. */
export function isExecutionTargetFieldDirty(value: unknown): boolean {
  if (value === true) {
    return true
  }
  if (Array.isArray(value)) {
    return value.some((entry) => isExecutionTargetFieldDirty(entry))
  }
  if (value && typeof value === 'object') {
    return Object.values(value).some((entry) => isExecutionTargetFieldDirty(entry))
  }
  return false
}

/**
 * Prefill the shared create/edit form from a loaded execution target.
 * OpenShift cluster stays read-only (resolved from integrations), matching configure.
 */
export function toExecutionTargetFormValues(target: ExecutionTargetRead): ExecutionTargetFormData {
  const placement = target.placement
  const namespace = placement?.type === 'kubernetes' ? placement.namespace : ''
  return {
    name: target.name,
    namespace,
    nodeSelectors: parseNodeSelectorPairs(getNodeSelectors(placement)),
  }
}

/** Map validated form values to the Execution Plane create payload. */
export function toExecutionTargetCreateBody(data: ExecutionTargetFormData): ExecutionTargetCreate {
  return {
    name: data.name.trim(),
    placement: buildKubernetesPlacement(data),
  }
}

/**
 * Build a partial PATCH body from dirty form fields only.
 * `is_default`, `enabled`, and `labels` are intentionally omitted — the configure UI does
 * not expose them, and default promotion remains a separate lifecycle concern.
 *
 * When placement is rebuilt, pass `existingTarget` so kubernetes kubernetes `tolerations`
 * are preserved (the form does not expose that field).
 */
export function toExecutionTargetUpdateBody(
  data: ExecutionTargetFormData,
  dirtyFields: ExecutionTargetDirtyFields,
  existingTarget?: ExecutionTargetRead
): ExecutionTargetUpdate {
  const body: ExecutionTargetUpdate = {}

  if (isExecutionTargetFieldDirty(dirtyFields.name)) {
    body.name = data.name.trim()
  }

  const placementDirty =
    isExecutionTargetFieldDirty(dirtyFields.namespace) || isExecutionTargetFieldDirty(dirtyFields.nodeSelectors)
  if (placementDirty) {
    body.placement = buildKubernetesPlacement(data, {
      tolerations: getExistingKubernetesTolerations(existingTarget),
    })
  }

  return body
}

/**
 * Map ExecutionTargetUpdate validation `loc` paths onto form field names.
 * Example: `placement.namespace` → `namespace`.
 */
export function mapExecutionTargetUpdateFieldPath(apiFieldPath: string): string {
  if (apiFieldPath === 'placement.namespace' || apiFieldPath === 'placement.type') {
    return 'namespace'
  }
  if (apiFieldPath === 'placement.node_selectors' || apiFieldPath.startsWith('placement.node_selectors.')) {
    return 'nodeSelectors'
  }
  return apiFieldPath
}

/** Form fields that can receive mapped server validation errors. */
export type ExecutionTargetFormErrorField = Extract<
  keyof ExecutionTargetFormData,
  'name' | 'namespace' | 'nodeSelectors'
>

/**
 * Resolve a server validation path to a known form field, or `null` when the path
 * does not map onto the edit form (ignore unexpected `loc` values).
 */
export function toExecutionTargetFormErrorField(apiFieldPath: string): ExecutionTargetFormErrorField | null {
  const mapped = mapExecutionTargetUpdateFieldPath(apiFieldPath)
  if (mapped === 'name' || mapped === 'namespace' || mapped === 'nodeSelectors') {
    return mapped
  }
  return null
}

export const EXECUTION_TARGET_FORM_DEFAULT_VALUES: ExecutionTargetFormData = {
  name: '',
  namespace: '',
  nodeSelectors: [{ key: '', value: '' }],
}
