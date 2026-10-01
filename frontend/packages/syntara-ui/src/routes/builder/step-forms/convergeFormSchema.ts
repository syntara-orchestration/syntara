import { z } from 'zod'

import { optionalNumber } from './shared/formSchemaUtils'
import { stepSettingsSchema } from './shared/stepSettingsSchema'

const positiveWholeNumber = optionalNumber
  .optional()
  .refine((value) => value === undefined || (Number.isInteger(value) && value >= 1), {
    message: 'Required path count must be a whole number greater than 0',
  })

/**
 * Zod schema for the Converge step form.
 * continue_on_failure lives in node settings (Settings tab).
 * wait_duration is a config field shown on the Parameters tab.
 */
const convergeFormSchemaBase = z.object({
  name: z.string(),
  strategy: z.enum(['all', 'any']).optional(),
  requiredPathCount: positiveWholeNumber,
  wait_duration: z.number().int().positive().optional(),
  settings: stepSettingsSchema.optional(),
})

export const convergeFormSchema = convergeFormSchemaBase

export type ConvergeFormData = z.infer<typeof convergeFormSchemaBase>
export type ConvergeStrategy = ConvergeFormData['strategy']
