import { z } from 'zod'

import type { Expression } from '../../../utils/expressions/types'

const switchCaseSchema = z.object({
  caseId: z.string(),
  label: z.string().optional(),
  condition: z.string().optional(),
  expressionTree: z.custom<Expression>().optional(),
  editorMode: z.enum(['visual', 'raw']).optional(),
})

export const switchFormSchema = z.object({
  name: z.string(),
  cases: z.array(switchCaseSchema),
})

export type SwitchFormData = z.infer<typeof switchFormSchema>
export type SwitchCaseData = z.infer<typeof switchCaseSchema>
