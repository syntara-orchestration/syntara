import { z } from 'zod'

import { validateExtraVars } from './shared/aapSchemaUtils'
import { optionalNumber } from './shared/formSchemaUtils'
import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

/**
 * Zod schema for the AAP (Ansible Automation Platform) job template node form.
 * Uses snake_case to match API contract.
 *
 * All fields are optional to allow adding incomplete nodes.
 * When extra_vars is provided, it must be valid JSON object format.
 */
export const aapJobTemplateSchema = z
  .object({
    name: z.string(),
    credential_id: z.string().optional(),
    integration_id: z.string().optional(),

    // ── Core fields (from cascading dropdowns) ────────────────────────
    organization_name: z.string().optional(),
    organization_id: optionalNumber.optional(),
    job_template_name: z.string().optional(),
    job_template_id: optionalNumber.optional(),

    // ── Prompt on Launch ──────────────────────────────────────────────
    inventory_name: z.string().optional(),
    inventory_id: optionalNumber.optional(),
    extra_vars: z.string().optional(),
    limit: z.string().optional(),
    tags: z.string().optional(),
    skip_tags: z.string().optional(),
    verbosity: z.string().optional(),
    job_credentials: z.array(z.number()).optional(),

    // ── Additional fields ─────────────────────────────────────────────
    job_type: z.string().optional(),
    forks: optionalNumber.optional(),
    job_slice_count: optionalNumber.optional(),
    diff_mode: z.boolean().optional(),
    execution_environment: z.string().optional(),
    execution_environment_id: optionalNumber.optional(),
    instance_group: z.string().optional(),
    instance_group_id: optionalNumber.optional(),
    labels: z.array(z.string()).optional(),
    settings: nodeSettingsSchema.optional(),
    // Local UI mode: persisted in node parameters so reopen restores the toggle
    use_input_variables: z.boolean().optional(),
  })
  .superRefine((data, ctx) => {
    validateExtraVars(data.extra_vars, ctx)
  })

export type AAPJobTemplateFormData = z.infer<typeof aapJobTemplateSchema>
