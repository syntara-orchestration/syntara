import { z } from 'zod'

import { APP_TITLE } from '../../../../utils/appTitle'

import { validateGroupJmespathExpression } from './groupMappingUtils'

export const GROUP_MAPPING_IDP_GROUP_VALUE_MAX_LENGTH = 255
export const GROUP_MAPPING_JMESPATH_EXPRESSION_MAX_LENGTH = 500

const groupMappingEditEntrySchema = z.object({
  idpGroupValue: z
    .string()
    .max(GROUP_MAPPING_IDP_GROUP_VALUE_MAX_LENGTH, 'IdP group value must be at most 255 characters'),
  mappedGroupId: z.union([z.literal(''), z.string().uuid(`Select a valid ${APP_TITLE} group`)]),
})

export const groupMappingEditFormSchema = z
  .object({
    expression: z
      .string()
      .min(1, 'Group extraction expression is required')
      .max(GROUP_MAPPING_JMESPATH_EXPRESSION_MAX_LENGTH, 'Group extraction expression must be at most 500 characters')
      .superRefine((value, ctx) => {
        const syntaxError = validateGroupJmespathExpression(value)
        if (syntaxError) {
          ctx.addIssue({ code: z.ZodIssueCode.custom, message: syntaxError })
        }
      }),
    entries: z.array(groupMappingEditEntrySchema),
  })
  .superRefine((data, ctx) => {
    data.entries.forEach((entry, index) => {
      const hasIdp = entry.idpGroupValue.trim().length > 0
      const hasMappedGroup = entry.mappedGroupId.trim().length > 0

      if (!hasIdp && !hasMappedGroup) {
        return
      }

      if (hasIdp && !hasMappedGroup) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Select a ${APP_TITLE} group`,
          path: ['entries', index, 'mappedGroupId'],
        })
      }

      if (!hasIdp && hasMappedGroup) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Enter an IdP group value',
          path: ['entries', index, 'idpGroupValue'],
        })
      }
    })
  })

export type GroupMappingEditFormValues = z.infer<typeof groupMappingEditFormSchema>
