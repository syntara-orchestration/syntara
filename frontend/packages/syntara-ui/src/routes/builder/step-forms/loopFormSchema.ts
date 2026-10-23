import { z } from 'zod'

import { optionalNumber } from './shared/formSchemaUtils'
import { stepSettingsSchema } from './shared/stepSettingsSchema'

const loopFormSchemaBase = z.object({
  name: z.string(),
  type: z.enum(['forEach', 'while']),
  items: z.string().optional(),
  indexVariable: z.string().optional(),
  itemVariable: z.string().optional(),
  condition: z.string().optional(),
  maxIterations: optionalNumber.optional(),
  settings: stepSettingsSchema.optional(),
})

export const loopFormSchema = loopFormSchemaBase

export type LoopFormData = z.infer<typeof loopFormSchemaBase>
