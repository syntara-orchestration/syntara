import { ExecutorTypeEnum } from '@syntara/contracts'
import { z } from 'zod'

import { parseJsonEnvironment } from '../../../utils/parseJsonEnvironment'
import { ScriptAffinityEnum } from '../utils/scriptExecutionProfile'

import { stepSettingsSchema } from './shared/stepSettingsSchema'

/**
 * Zod schema for the Action step form.
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

const scriptFormFields = {
  name: z.string(),
  code: z.string().min(1, 'Script code is required'),
  parameters: optionalJsonObjectSchema,
  affinity: z.enum([ScriptAffinityEnum.NONE, ScriptAffinityEnum.REQUIRED_TARGET]).default(ScriptAffinityEnum.NONE),
  execution_target_id: z.uuid('Select a valid execution target').optional(),
  settings: stepSettingsSchema.optional(),
}

const pythonScriptActionSchema = z.object({
  executor: z.literal(ExecutorTypeEnum.SCRIPT_PYTHON),
  ...scriptFormFields,
})

const bashScriptActionSchema = z.object({
  executor: z.literal(ExecutorTypeEnum.SCRIPT_BASH),
  ...scriptFormFields,
})

const apiActionSchema = z.object({
  executor: z.literal(ExecutorTypeEnum.HTTP_REQUEST),
  name: z.string(),
  code: z.string().optional(),
  method: httpMethodSchema.optional(),
  url: z.string().optional(),
  headers: z.array(keyValueEntrySchema).optional(),
  body: z.string().optional(),
  parameters: z.string().optional(),
  credential_id: z.string().optional(),
  settings: stepSettingsSchema.optional(),
})

export const actionFormSchema = z
  .discriminatedUnion('executor', [pythonScriptActionSchema, bashScriptActionSchema, apiActionSchema])
  .superRefine((data, context) => {
    if (
      (data.executor === ExecutorTypeEnum.SCRIPT_PYTHON || data.executor === ExecutorTypeEnum.SCRIPT_BASH) &&
      data.affinity === ScriptAffinityEnum.REQUIRED_TARGET &&
      !data.execution_target_id?.trim()
    ) {
      context.addIssue({
        code: 'custom',
        path: ['execution_target_id'],
        message: 'Execution target is required',
      })
    }
  })

/** Validated form output (discriminated union). */
export type ActionFormData = z.infer<typeof actionFormSchema>

/** Form state / input type (allows empty code/url before validation). */
export type ActionFormValues = z.input<typeof actionFormSchema>
