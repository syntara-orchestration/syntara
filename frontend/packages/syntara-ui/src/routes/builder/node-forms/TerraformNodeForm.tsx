import { Alert } from '@patternfly/react-core'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo, useState } from 'react'
import { FormProvider, useForm, useWatch, type FieldPath } from 'react-hook-form'

import { SynSelectField } from '../../../components/forms/SynSelectField'
import { SynSwitchField } from '../../../components/forms/SynSwitchField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { CredentialSelector } from '../components/CredentialSelector'
import { TFEIntegrationSelector } from '../components/TFEIntegrationSelector'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { ActivityNameField } from './shared/ActivityNameField'
import { NodeFormContainer } from './shared/NodeFormContainer'

export type TerraformNodeFormData = {
  name: string
  integration_id?: string
  credential_id?: string
  organization?: string
  name_field?: string
  workspace_id?: string
  variable_id?: string
  key?: string
  value?: string
  category?: 'terraform' | 'env'
  sensitive?: boolean
  hcl?: boolean
  force?: boolean
  mode?: string
  run_id?: string
  comment?: string
  artifact?: string
  installation_id?: string
  repository?: string
  branch?: string
  project_id?: string
  team_id?: string
  access?: string
  description?: string
  wait_for_completion?: boolean
  search?: string
  target_resources?: string
  replace_resources?: string
  configuration_version_id?: string
  auto_apply?: boolean
  terraform_version?: string
  execution_mode?: 'remote' | 'local' | 'agent'
  preset?: 'remote_no_vcs' | 'agent' | 'remote_oauth_vcs' | 'remote_github'
  agent_pool_id?: string
  oauth_token_id?: string
  github_app_installation_id?: string
}

type TerraformNodeFormProps = {
  onSubmit: (data: TerraformNodeFormData) => void
  onCancel?: () => void
  initialData?: Partial<TerraformNodeFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
  projectId?: string
  /** Registry subtype id (e.g. tfe-create-workspace) used to show relevant fields */
  subtypeId?: string
}

const SUBTYPE_FIELDS: Record<string, FieldPath<TerraformNodeFormData>[]> = {
  'tfe-create-workspace': ['name_field', 'organization', 'preset', 'auto_apply', 'terraform_version', 'description'],
  'tfe-list-workspaces': ['organization', 'search', 'project_id'],
  'tfe-update-workspace': ['workspace_id', 'preset', 'auto_apply', 'description', 'terraform_version'],
  'tfe-delete-workspace': ['workspace_id', 'force'],
  'tfe-fetch-state-outputs': ['workspace_id'],
  'tfe-add-variable': ['workspace_id', 'key', 'value', 'category', 'sensitive', 'hcl'],
  'tfe-list-variables': ['workspace_id', 'key'],
  'tfe-update-variable': ['variable_id', 'value', 'hcl', 'category'],
  'tfe-delete-variable': ['variable_id'],
  'tfe-upload-configuration-version': ['workspace_id', 'artifact'],
  'tfe-trigger-run': [
    'workspace_id',
    'mode',
    'configuration_version_id',
    'target_resources',
    'replace_resources',
    'comment',
  ],
  'tfe-get-run-status': ['run_id', 'wait_for_completion'],
  'tfe-apply-run': ['run_id', 'comment'],
  'tfe-discard-run': ['run_id', 'comment'],
  'tfe-cancel-run': ['run_id', 'comment'],
  'tfe-force-cancel-run': ['run_id', 'comment'],
  'tfe-list-runs': ['workspace_id'],
  'tfe-add-run-comment': ['run_id', 'comment'],
  'tfe-list-github-installations': [],
  'tfe-get-github-installation': ['installation_id'],
  'tfe-link-vcs': ['workspace_id', 'installation_id', 'repository', 'branch'],
  'tfe-create-project': ['name_field', 'description'],
  'tfe-list-projects': [],
  'tfe-get-project': ['project_id'],
  'tfe-update-project': ['project_id', 'name_field', 'description'],
  'tfe-delete-project': ['project_id'],
  'tfe-move-workspace-to-project': ['workspace_id', 'project_id'],
  'tfe-assign-team-permissions': ['project_id', 'team_id', 'access'],
}

const FIELD_LABELS: Partial<Record<FieldPath<TerraformNodeFormData>, string>> = {
  name_field: 'Name',
  organization: 'Organization override',
  workspace_id: 'Workspace ID',
  variable_id: 'Variable ID',
  key: 'Variable key',
  value: 'Variable value',
  category: 'Category (terraform|env)',
  mode: 'Run mode',
  run_id: 'Run ID',
  comment: 'Comment / message',
  artifact: 'Artifact (base64 .tar.gz)',
  installation_id: 'GitHub installation ID',
  repository: 'Repository name',
  branch: 'Branch',
  project_id: 'Project ID',
  team_id: 'Team ID',
  access: 'Access (read|admin|...)',
  description: 'Description',
  search: 'Search',
  target_resources: 'Target resources (comma-separated)',
  replace_resources: 'Replace resources (comma-separated)',
  configuration_version_id: 'Configuration version ID',
  terraform_version: 'Terraform version',
  execution_mode: 'Execution mode (remote|local)',
  preset: 'Preset',
  agent_pool_id: 'Agent pool ID',
  oauth_token_id: 'OAuth token ID',
  github_app_installation_id: 'GitHub App installation ID',
  sensitive: 'Sensitive',
  hcl: 'HCL',
  force: 'Force delete',
  wait_for_completion: 'Wait for completion',
  auto_apply: 'Auto apply',
}

const WORKSPACE_PRESET_OPTIONS = [
  { value: 'remote_no_vcs', label: 'Remote (no VCS)' },
  { value: 'agent', label: 'Agent execution' },
  { value: 'remote_oauth_vcs', label: 'Remote + OAuth VCS' },
  { value: 'remote_github', label: 'Remote + GitHub' },
] as const

const PRESET_EXTRA_FIELDS: Partial<
  Record<NonNullable<TerraformNodeFormData['preset']>, FieldPath<TerraformNodeFormData>[]>
> = {
  agent: ['agent_pool_id'],
  remote_oauth_vcs: ['repository', 'branch', 'oauth_token_id'],
  remote_github: ['repository', 'branch', 'github_app_installation_id'],
}

const BOOLEAN_FIELDS = new Set<FieldPath<TerraformNodeFormData>>([
  'sensitive',
  'hcl',
  'force',
  'wait_for_completion',
  'auto_apply',
])

export function TerraformNodeForm({
  onSubmit,
  initialData,
  onHeaderContentChange,
  projectId,
  subtypeId = 'tfe-create-workspace',
}: Readonly<TerraformNodeFormProps>) {
  const isVersionView = useIsVersionView()
  const methods = useForm<TerraformNodeFormData>({
    defaultValues: {
      name: '',
      category: 'terraform',
      mode: 'plan-only',
      access: 'read',
      sensitive: false,
      hcl: false,
      force: false,
      wait_for_completion: false,
      auto_apply: false,
      ...(subtypeId === 'tfe-create-workspace' ? { preset: 'remote_no_vcs' as const } : {}),
      ...initialData,
    },
  })
  const { control, register, handleSubmit, setValue } = methods
  const integrationId = useWatch({ control, name: 'integration_id' })
  const credentialId = useWatch({ control, name: 'credential_id' })
  const preset = useWatch({ control, name: 'preset' })
  const [staleWarning, setStaleWarning] = useState('')

  const fields = useMemo(() => {
    const base = SUBTYPE_FIELDS[subtypeId] ?? []
    if (!base.includes('preset')) return base
    return [...base, ...(PRESET_EXTRA_FIELDS[preset ?? 'remote_no_vcs'] ?? [])]
  }, [subtypeId, preset])

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="tfe-name" ariaLabel="Name" />,
    [register]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, onSubmit)

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="terraform-node-form" onSubmit={handleSubmit(onSubmit)}>
        <TFEIntegrationSelector
          value={integrationId}
          onChange={(id) => {
            setValue('integration_id', id, { shouldDirty: true })
            if (!id) setValue('credential_id', undefined, { shouldDirty: true })
            setStaleWarning('')
          }}
          onStaleDetected={() => {
            setValue('integration_id', undefined, { shouldDirty: true })
            setValue('credential_id', undefined, { shouldDirty: true })
            setStaleWarning('The previously selected TFE integration is no longer available.')
          }}
          isDisabled={isVersionView}
          isRequired
          projectId={projectId}
        />
        {staleWarning ? <Alert variant="warning" isInline isPlain title={staleWarning} /> : null}
        <CredentialSelector
          value={credentialId}
          onChange={(id) => setValue('credential_id', id, { shouldDirty: true })}
          compatibleTypeNames={['HTTP Bearer Token']}
          isDisabled={isVersionView || !integrationId}
          isRequired
          projectId={projectId}
        />
        {fields.map((field) => {
          const fieldId = `tfe-${field}`
          const label = FIELD_LABELS[field] ?? field
          if (field === 'preset') {
            return (
              <SynSelectField
                key={field}
                name="preset"
                control={control}
                label={label}
                fieldId={fieldId}
                options={[...WORKSPACE_PRESET_OPTIONS]}
                isDisabled={isVersionView}
                isRequired
              />
            )
          }
          if (BOOLEAN_FIELDS.has(field)) {
            return (
              <SynSwitchField
                key={field}
                name={field}
                control={control}
                label={label}
                fieldId={fieldId}
                isDisabled={isVersionView}
              />
            )
          }
          return (
            <SynTextField
              key={field}
              name={field}
              control={control}
              label={label}
              fieldId={fieldId}
              isDisabled={isVersionView}
            />
          )
        })}
      </NodeFormContainer>
    </FormProvider>
  )
}
