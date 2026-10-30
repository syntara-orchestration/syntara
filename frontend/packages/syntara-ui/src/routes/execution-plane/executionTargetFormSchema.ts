import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { z } from 'zod'

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

/** Map validated form values to the Execution Plane create payload. */
export function toExecutionTargetCreateBody(data: ExecutionTargetFormData): ExecutionTargetCreate {
  const node_selectors = data.nodeSelectors
    .map((pair) => ({ key: pair.key.trim(), value: pair.value.trim() }))
    .filter((pair) => pair.key.length > 0)
    .map((pair) => `${pair.key}=${pair.value}`)

  return {
    name: data.name.trim(),
    placement: {
      type: 'kubernetes',
      namespace: data.namespace.trim(),
      ...(node_selectors.length > 0 ? { node_selectors } : {}),
    },
  }
}

export const EXECUTION_TARGET_FORM_DEFAULT_VALUES: ExecutionTargetFormData = {
  name: '',
  namespace: '',
  nodeSelectors: [{ key: '', value: '' }],
}
