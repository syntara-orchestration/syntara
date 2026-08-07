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
