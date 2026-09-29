import { z } from 'zod'

import { formDefinitionSchema } from '../../../forms'

import { optionalNumber } from './shared/formSchemaUtils'
import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

const MAX_RESPONDER_USERS = 100
const MAX_RESPONDER_GROUPS = 50

export const formPromptFormSchema = z.object({
  name: z.string(),
  message: z.string().max(2000).nullable().optional(),
  form_definition: formDefinitionSchema,
  responder_users: z
    .array(z.string())
    .max(MAX_RESPONDER_USERS, `Cannot select more than ${MAX_RESPONDER_USERS} users`)
    .optional(),
  responder_groups: z
    .array(z.string())
    .max(MAX_RESPONDER_GROUPS, `Cannot select more than ${MAX_RESPONDER_GROUPS} groups`)
    .optional(),
  response_window: optionalNumber.optional(),
  fallback_decision: z.enum(['submit', 'fallback']).nullable().optional(),
  submit_label: z.string().max(64).optional(),
  success_message: z.string().max(500).optional(),
  timezone: z.string().max(64).optional(),
  css_override: z.string().max(10000).optional(),
  settings: nodeSettingsSchema.optional(),
})

export type FormPromptFormData = z.infer<typeof formPromptFormSchema>

/** Parsed shape for `Activity.parameters` on form_prompt nodes (load/edit path). */
export const formPromptStoredParametersSchema = formPromptFormSchema
  .pick({
    message: true,
    form_definition: true,
    responder_users: true,
    responder_groups: true,
    response_window: true,
    fallback_decision: true,
    submit_label: true,
    success_message: true,
    timezone: true,
    css_override: true,
  })
  .extend({
    fallback_behavior: z.enum(['fail', 'fallback']).nullable().optional(),
  })
  .partial()

export type FormPromptStoredParameters = z.infer<typeof formPromptStoredParametersSchema>
