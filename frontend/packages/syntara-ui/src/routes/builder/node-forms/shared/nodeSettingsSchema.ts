import { z } from 'zod'

const retryPolicySchema = z.object({
  max_retries: z.number().int().min(0).optional(),
  backoff: z.enum(['exponential', 'fixed']).optional(),
  initial_interval: z.number().int().positive().optional(),
  max_interval: z.number().int().positive().optional(),
  backoff_coefficient: z.number().min(1).optional(),
})

export const nodeSettingsSchema = z.object({
  continue_on_failure: z.boolean().optional(),
  timeout: z.number().int().positive().optional(),
  retry_policy: retryPolicySchema.optional(),
})

export type NodeSettingsFormData = z.infer<typeof nodeSettingsSchema>
export type RetryPolicyFormData = z.infer<typeof retryPolicySchema>

/** Drop unset optional fields so "System default" clears a previously explicit node override. */
export function persistNodeSettings(settings?: NodeSettingsFormData): NodeSettingsFormData | undefined {
  if (!settings) return undefined
  const next: NodeSettingsFormData = { ...settings }
  if (next.continue_on_failure === undefined) {
    delete next.continue_on_failure
  }
  return Object.keys(next).length > 0 ? next : undefined
}
