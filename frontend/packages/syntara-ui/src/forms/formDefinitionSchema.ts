import type { FormDefinition } from '@syntara/contracts'
import { z } from 'zod'

import {
  FORM_DEFINITION_MAX_FIELDS,
  FORM_DEFINITION_MIN_FIELDS,
  FORM_FIELD_LABEL_MAX_LENGTH,
  FORM_FIELD_VALUE_NAME_MAX_LENGTH,
  FORM_STATIC_OPTION_LABEL_MAX_LENGTH,
  FORM_STATIC_OPTIONS_MAX_LENGTH,
  isValidFormFieldValueName,
} from './formConstants'
import { FormFieldTypeEnum } from './formFieldTypeEnum'
import { FormDefinitionValidationError, type FormFieldValidationError } from './formValidationErrors'

const fieldValueNameSchema = z
  .string()
  .min(1)
  .max(FORM_FIELD_VALUE_NAME_MAX_LENGTH)
  .refine(isValidFormFieldValueName, 'Value name must start with a letter or underscore')

const fieldLabelSchema = z.string().min(1).max(FORM_FIELD_LABEL_MAX_LENGTH)

const formFieldBaseSchema = z.object({
  value_name: fieldValueNameSchema,
  label: fieldLabelSchema,
  placeholder: z.string().nullable().optional(),
  help_text: z.string().nullable().optional(),
  required: z.boolean().optional(),
})

const staticOptionSchema = z.object({
  display_label: z.string().min(1).max(FORM_STATIC_OPTION_LABEL_MAX_LENGTH),
  value: z.string(),
})

const staticOptionsSchema = z.object({
  source: z.literal('static'),
  values: z.array(staticOptionSchema).min(1).max(FORM_STATIC_OPTIONS_MAX_LENGTH),
})

const dynamicOptionsSchema = z.object({
  source: z.literal('dynamic'),
  expression: z.string().min(1),
  label_key: z.string().min(1),
  value_key: z.string().min(1),
})

const resolvedOptionSchema = z.object({
  display_label: z.string().min(1).max(FORM_STATIC_OPTION_LABEL_MAX_LENGTH),
  value: z.union([z.string(), z.number(), z.boolean()]),
})

const resolvedOptionsSchema = z.object({
  source: z.literal('dynamic_resolved'),
  values: z.array(resolvedOptionSchema).min(1).max(FORM_STATIC_OPTIONS_MAX_LENGTH),
})

const optionsSourceSchema = z.discriminatedUnion('source', [
  staticOptionsSchema,
  dynamicOptionsSchema,
  resolvedOptionsSchema,
])

const textFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.TEXT),
  default: z.string().nullable().optional(),
})

const textAreaFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.TEXTAREA),
  default: z.string().nullable().optional(),
})

const maskedTextFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.MASKED_TEXT),
  default: z.string().nullable().optional(),
})

const emailFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.EMAIL),
  default: z.string().nullable().optional(),
})

const numberFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.NUMBER),
  default: z.union([z.number(), z.null()]).optional(),
})

const checkboxFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.CHECKBOX),
  default: z.boolean().optional(),
})

const isoDateSchema = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, 'Date must be an ISO 8601 date in YYYY-MM-DD format')
  .refine((value) => {
    const year = Number(value.slice(0, 4))
    const parsed = new Date(`${value}T00:00:00.000Z`)
    return year > 0 && !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
  }, 'Date must be a valid ISO 8601 calendar date')

const dateValueSchema = z.object({
  date: isoDateSchema.nullable().optional(),
  time: z
    .string()
    .regex(/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/, 'Time must use 24-hour HH:MM format')
    .nullable()
    .optional(),
  timezone: z
    .string()
    .max(64)
    .refine((value) => {
      try {
        new Intl.DateTimeFormat('en-US', { timeZone: value })
        return true
      } catch {
        return false
      }
    }, 'Timezone must be a valid IANA timezone name')
    .nullable()
    .optional(),
})

const DATE_COMPONENTS = ['date', 'time', 'timezone'] as const

const dateFieldSchema = formFieldBaseSchema
  .extend({
    type: z.literal(FormFieldTypeEnum.DATE),
    include_date: z.boolean().optional(),
    include_time: z.boolean().optional(),
    include_timezone: z.boolean().optional(),
    default: dateValueSchema.nullable().optional(),
  })
  .superRefine((field, ctx) => {
    const included = {
      date: field.include_date ?? true,
      time: field.include_time ?? false,
      timezone: field.include_timezone ?? false,
    }

    if (!included.date && !included.time && !included.timezone) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'At least one of include_date, include_time, or include_timezone must be true',
        path: ['include_date'],
      })
    }

    // A wall-clock time is ambiguous without the zone it is read in.
    if (included.time && !included.timezone) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'include_timezone is required when include_time is true',
        path: ['include_timezone'],
      })
    }

    // A default stands in for a whole skipped answer, so it must be complete.
    if (field.default == null) return

    for (const component of DATE_COMPONENTS) {
      const supplied = field.default[component] != null
      if (included[component] && !supplied) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Default is missing ${component}`,
          path: ['default', component],
        })
      } else if (!included[component] && supplied) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `Default supplies ${component}, which this field does not collect`,
          path: ['default', component],
        })
      }
    }
  })

const dropdownFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.DROPDOWN),
  options: optionsSourceSchema,
  default: z.union([z.string(), z.number(), z.boolean(), z.null()]).optional(),
})

const multiSelectFieldSchema = formFieldBaseSchema.extend({
  type: z.literal(FormFieldTypeEnum.MULTI_SELECT),
  options: optionsSourceSchema,
  default: z
    .array(z.union([z.string(), z.number(), z.boolean()]))
    .nullable()
    .optional(),
})

export const formFieldSchema = z.discriminatedUnion('type', [
  textFieldSchema,
  textAreaFieldSchema,
  maskedTextFieldSchema,
  emailFieldSchema,
  numberFieldSchema,
  checkboxFieldSchema,
  dateFieldSchema,
  dropdownFieldSchema,
  multiSelectFieldSchema,
])

function findDuplicateFieldNames(fields: ReadonlyArray<{ value_name: string }>): string[] {
  const duplicateNames: string[] = []
  const nameCounts = new Map<string, number>()
  for (const field of fields) {
    const name = field.value_name
    const seen = nameCounts.get(name) ?? 0
    nameCounts.set(name, seen + 1)
    if (seen === 1) {
      duplicateNames.push(name)
    }
  }
  return duplicateNames.slice().sort((a, b) => a.localeCompare(b, 'en'))
}

function validateMultiSelectDefault(
  field: Extract<z.infer<typeof formFieldSchema>, { type: typeof FormFieldTypeEnum.MULTI_SELECT }>,
  validValues: ReadonlySet<string | number | boolean>,
  index: number,
  ctx: z.RefinementCtx
): void {
  if (field.default == null) {
    return
  }
  const invalidDefaults: typeof field.default = []
  for (const value of field.default) {
    if (!validValues.has(value)) {
      invalidDefaults.push(value)
    }
  }
  if (invalidDefaults.length === 0) {
    return
  }
  ctx.addIssue({
    code: 'custom',
    message: `Field '${field.value_name}': default values ${JSON.stringify(invalidDefaults)} are not in the option list`,
    path: ['fields', index, 'default'],
  })
}

function validateDropdownDefault(
  field: Extract<z.infer<typeof formFieldSchema>, { type: typeof FormFieldTypeEnum.DROPDOWN }>,
  validValues: ReadonlySet<string | number | boolean>,
  index: number,
  ctx: z.RefinementCtx
): void {
  if (field.default == null || validValues.has(field.default)) {
    return
  }
  ctx.addIssue({
    code: 'custom',
    message: `Field '${field.value_name}': default value '${String(field.default)}' is not in the option list`,
    path: ['fields', index, 'default'],
  })
}

function validateOptionDefaults(fields: ReadonlyArray<z.infer<typeof formFieldSchema>>, ctx: z.RefinementCtx): void {
  for (const [index, field] of fields.entries()) {
    if (
      (field.type !== FormFieldTypeEnum.DROPDOWN && field.type !== FormFieldTypeEnum.MULTI_SELECT) ||
      (field.options.source !== 'static' && field.options.source !== 'dynamic_resolved')
    ) {
      continue
    }

    const validValues = new Set(field.options.values.map((option) => option.value))

    if (field.type === FormFieldTypeEnum.MULTI_SELECT) {
      validateMultiSelectDefault(field, validValues, index, ctx)
    } else {
      validateDropdownDefault(field, validValues, index, ctx)
    }
  }
}

export const formDefinitionSchema = z
  .object({
    fields: z.array(formFieldSchema).min(FORM_DEFINITION_MIN_FIELDS).max(FORM_DEFINITION_MAX_FIELDS),
  })
  .superRefine((definition, ctx) => {
    const sortedDuplicates = findDuplicateFieldNames(definition.fields)
    if (sortedDuplicates.length > 0) {
      ctx.addIssue({
        code: 'custom',
        message: `Duplicate field names are not allowed: ${sortedDuplicates.join(', ')}`,
        path: ['fields'],
      })
    }

    validateOptionDefaults(definition.fields, ctx)
  })

function zodPathToField(path: ReadonlyArray<PropertyKey>): string {
  const segments = path.map(String)
  if (segments.length >= 2 && segments[0] === 'fields' && !Number.isNaN(Number(segments[1]))) {
    const fieldPath = `fields[${segments[1]}]`
    const propertyPath = segments.slice(2).join('.')
    return propertyPath ? `${fieldPath}.${propertyPath}` : fieldPath
  }
  return segments.join('.')
}

function mapZodIssuesToFieldErrors(issues: z.ZodIssue[]): FormFieldValidationError[] {
  return issues.map((issue) => ({
    field: zodPathToField(issue.path),
    label: zodPathToField(issue.path),
    code: 'invalid_default' as const,
    message: issue.message,
  }))
}

/**
 * Parse and validate a form definition (shape + cross-field rules).
 * Throws {@link FormDefinitionValidationError} when invalid.
 */
export function parseFormDefinition(input: unknown): FormDefinition {
  const result = formDefinitionSchema.safeParse(input)
  if (!result.success) {
    throw new FormDefinitionValidationError(mapZodIssuesToFieldErrors(result.error.issues))
  }
  return result.data
}

/**
 * Non-throwing parse — returns `{ success: true, data }` or `{ success: false, errors }`.
 */
export function safeParseFormDefinition(
  input: unknown
): { success: true; data: FormDefinition } | { success: false; errors: FormFieldValidationError[] } {
  const result = formDefinitionSchema.safeParse(input)
  if (!result.success) {
    return { success: false, errors: mapZodIssuesToFieldErrors(result.error.issues) }
  }
  return { success: true, data: result.data }
}

export type FormDefinitionSchemaInput = z.input<typeof formDefinitionSchema>
export type FormFieldSchemaInput = z.input<typeof formFieldSchema>
