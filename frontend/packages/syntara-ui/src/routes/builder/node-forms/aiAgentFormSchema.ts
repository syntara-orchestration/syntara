import { z } from 'zod'

import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

/**
 * Zod schema for the AI Agent node form.
 * Single source of truth for shape and client-side validation.
 */
export const aiAgentFormSchema = z
  .object({
    name: z.string(),
    llm_model_id: z.string().optional(),
    prompt: z.string().optional(),
    tool_selection_strategy: z.enum(['ALL', 'NONE', 'SELECTED']).optional(),
    tool_selections: z.array(z.string()).optional(),
    integration_connections: z.array(z.object({ integration_id: z.string(), credential_id: z.string() })).optional(),
    credential_id: z.string().optional(),
    responseSchema: z.string().optional(),
    settings: nodeSettingsSchema.optional(),
  })
  .superRefine((data, ctx) => {
    const v = data.responseSchema?.trim()
    if (!v) return

    let parsed: unknown
    try {
      parsed = JSON.parse(v)
    } catch {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['responseSchema'],
        message: 'Invalid JSON',
      })
      return
    }

    if (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object') {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['responseSchema'],
        message: 'Response schema must be a JSON object',
      })
    }
  })

export type AIAgentFormData = z.infer<typeof aiAgentFormSchema>
