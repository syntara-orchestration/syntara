import { ExecutorTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { parseJsonEnvironment } from '../../../utils/parseJsonEnvironment'

import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

/**
 * Zod schema for the Action node form.
 * Uses discriminatedUnion on executor: script requires code, api requires url.
 */
const httpMethodSchema = z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])

const optionalJsonObjectSchema = z
  .string()
  .optional()
  .refine(
    (val) => {
      if (!val) return true
      return parseJsonEnvironment(val) !== undefined
    },
    { message: 'Must be a valid JSON object with string values, e.g. {"MY_VAR": "value"}' }
  )

const keyValueEntrySchema = z.object({
  id: z.string(),
  key: z.string(),
  value: z.string(),
})

const scriptActionSchema = z.object({
  executor: z.literal(ExecutorTypeEnum.SCRIPT),
  name: z.string(),
  code: z.string().optional(),
  language: z.string().optional(),
  method: httpMethodSchema.optional(),
  url: z.string().optional(),
  headers: z.array(keyValueEntrySchema).optional(),
  body: z.string().optional(),
  parameters: optionalJsonObjectSchema,
  credential_id: z.string().optional(),
  settings: nodeSettingsSchema.optional(),
})

const apiActionSchema = z.object({
  executor: z.literal(ExecutorTypeEnum.HTTP_REQUEST),
  name: z.string(),
  code: z.string().optional(),
  language: z.string().optional(),
  method: httpMethodSchema.optional(),
  url: z.string().optional(),
  headers: z.array(keyValueEntrySchema).optional(),
  body: z.string().optional(),
  parameters: z.string().optional(),
  credential_id: z.string().optional(),
  settings: nodeSettingsSchema.optional(),
})

export const actionFormSchema = z.discriminatedUnion('executor', [scriptActionSchema, apiActionSchema])

/** Validated form output (discriminated union). */
export type ActionFormData = z.infer<typeof actionFormSchema>

/** Form state / input type (allows empty code/url before validation). */
export type ActionFormValues = z.input<typeof actionFormSchema>
