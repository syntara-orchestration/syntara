import { Stack, StackItem, Title } from '@patternfly/react-core'

import type {
  AAPCredential,
  AAPExecutionEnvironment,
  AAPInstanceGroup,
  AAPInventory,
  AAPJobTemplateDetail,
  AAPLabel,
} from '../../../hooks/useAAPBrowser'
import type { ExpandableCodeEditorHandle } from '../components/ExpandableCodeEditor'

import { AAPLabelsField } from './AAPLabelsField'
import {
  DiffModeField,
  ExtraVariablesField,
  NumberInputField,
  RunTypeField,
  TagInputField,
  TextInputField,
  VerbosityField,
} from './AAPPromptFields'
import { AAPResourceMultiSelectField } from './AAPResourceMultiSelectField'
import { AAPResourceSelectField } from './AAPResourceSelectField'
import { stepHelp } from './shared/stepFieldHelp'

type PromptOnLaunchFieldsProps = {
  readonly extraVarsEditorRef: React.RefObject<ExpandableCodeEditorHandle | null>
  readonly templateDetail?: AAPJobTemplateDetail
  readonly isLoadingDetail?: boolean
  readonly inventories?: AAPInventory[]
  readonly loadingInventories?: boolean
  readonly executionEnvironments?: AAPExecutionEnvironment[]
  readonly loadingExecutionEnvironments?: boolean
  readonly credentials?: AAPCredential[]
  readonly loadingCredentials?: boolean
  readonly instanceGroups?: AAPInstanceGroup[]
  readonly loadingInstanceGroups?: boolean
  readonly labels?: AAPLabel[]
  readonly loadingLabels?: boolean
  readonly onSearchInventories?: (search: string) => void
  readonly onSearchExecutionEnvironments?: (search: string) => void
  readonly onSearchCredentials?: (search: string) => void
  readonly onSearchInstanceGroups?: (search: string) => void
  readonly onSearchLabels?: (search: string) => void
}

/** All ask_* flag keys that control field visibility. */
const PROMPT_FLAGS = [
  'ask_job_type_on_launch',
  'ask_inventory_on_launch',
  'ask_variables_on_launch',
  'ask_limit_on_launch',
  'ask_tags_on_launch',
  'ask_skip_tags_on_launch',
  'ask_verbosity_on_launch',
  'ask_diff_mode_on_launch',
  'ask_forks_on_launch',
  'ask_job_slice_count_on_launch',
  'ask_execution_environment_on_launch',
  'ask_credential_on_launch',
  'ask_instance_groups_on_launch',
  'ask_labels_on_launch',
  'ask_timeout_on_launch',
] as const

function hasAnyPromptFlag(detail: AAPJobTemplateDetail): boolean {
  return PROMPT_FLAGS.some((flag) => detail[flag])
}

// ── Field components ───────────────────────────────

type InventoryFieldProps = {
  readonly inventories: readonly AAPInventory[]
  readonly loadingInventories: boolean
  readonly defaultName: string | undefined
  readonly onSearchInventories: (search: string) => void
}

function InventoryField({ inventories, loadingInventories, defaultName, onSearchInventories }: InventoryFieldProps) {
  return (
    <AAPResourceSelectField
      label="Inventory"
      fieldId="aap-inventory"
      nameField="inventory_name"
      idField="inventory_id"
      items={inventories}
      isLoading={loadingInventories}
      helperText={
        defaultName
          ? `Override default inventory for the job. Default: ${defaultName}`
          : 'Override default inventory for the job'
      }
      labelHelp={stepHelp.aapInventory}
      placeholderText={defaultName ? `${defaultName} (default)` : 'No default inventory'}
      onSearchChange={onSearchInventories}
    />
  )
}

type ExecutionEnvironmentFieldProps = {
  readonly executionEnvironments: readonly AAPExecutionEnvironment[]
  readonly loadingExecutionEnvironments: boolean
  readonly defaultName: string | undefined
  readonly onSearchExecutionEnvironments: (search: string) => void
}

function ExecutionEnvironmentField({
  executionEnvironments,
  loadingExecutionEnvironments,
  defaultName,
  onSearchExecutionEnvironments,
}: ExecutionEnvironmentFieldProps) {
  return (
    <AAPResourceSelectField
      label="Execution environment"
      fieldId="aap-executionEnvironment"
      nameField="execution_environment"
      idField="execution_environment_id"
      items={executionEnvironments}
      isLoading={loadingExecutionEnvironments}
      helperText={
        defaultName
          ? `Override default execution environment for the job. Default: ${defaultName}`
          : 'Override default execution environment for the job'
      }
      placeholderText={defaultName ? `${defaultName} (default)` : 'No default execution environment'}
      labelHelp={stepHelp.aapExecutionEnvironment}
      onSearchChange={onSearchExecutionEnvironments}
    />
  )
}

// ── Main component ──────────────────────────────────────────────────────

function PromptOnLaunchFieldList({
  templateDetail,
  inventories,
  loadingInventories,
  executionEnvironments,
  loadingExecutionEnvironments,
  credentials,
  loadingCredentials,
  instanceGroups,
  loadingInstanceGroups,
  labels,
  loadingLabels,
  extraVarsEditorRef,
  onSearchInventories,
  onSearchExecutionEnvironments,
  onSearchCredentials,
  onSearchInstanceGroups,
  onSearchLabels,
}: {
  readonly templateDetail: AAPJobTemplateDetail
  readonly inventories: AAPInventory[]
  readonly loadingInventories: boolean
  readonly executionEnvironments: AAPExecutionEnvironment[]
  readonly loadingExecutionEnvironments: boolean
  readonly credentials: AAPCredential[]
  readonly loadingCredentials: boolean
  readonly instanceGroups: AAPInstanceGroup[]
  readonly loadingInstanceGroups: boolean
  readonly labels: AAPLabel[]
  readonly loadingLabels: boolean
  readonly extraVarsEditorRef: React.RefObject<ExpandableCodeEditorHandle | null>
  readonly onSearchInventories: (search: string) => void
  readonly onSearchExecutionEnvironments: (search: string) => void
  readonly onSearchCredentials: (search: string) => void
  readonly onSearchInstanceGroups: (search: string) => void
  readonly onSearchLabels: (search: string) => void
}) {
  const inventoryDefaultName = templateDetail.default_inventory?.name
  const executionEnvironmentDefaultName = templateDetail.default_execution_environment?.name

  return (
    <>
      {templateDetail.ask_job_type_on_launch && <RunTypeField />}
      {templateDetail.ask_inventory_on_launch && (
        <InventoryField
          inventories={inventories}
          loadingInventories={loadingInventories}
          defaultName={inventoryDefaultName}
          onSearchInventories={onSearchInventories}
        />
      )}
      {templateDetail.ask_execution_environment_on_launch && (
        <ExecutionEnvironmentField
          executionEnvironments={executionEnvironments}
          loadingExecutionEnvironments={loadingExecutionEnvironments}
          defaultName={executionEnvironmentDefaultName}
          onSearchExecutionEnvironments={onSearchExecutionEnvironments}
        />
      )}
      {templateDetail.ask_credential_on_launch && (
        <AAPResourceMultiSelectField
          label="Credentials"
          fieldId="aap-credentials"
          nameField="job_credentials"
          items={credentials}
          isLoading={loadingCredentials}
          helperText="Select one or more credentials for the job"
          placeholderText="No default credentials"
          defaultValues={templateDetail.default_credentials}
          onSearchChange={onSearchCredentials}
          labelHelp={stepHelp.aapJobCredentials}
        />
      )}
      {templateDetail.ask_labels_on_launch && (
        <AAPLabelsField
          label="Labels"
          fieldId="aap-labels"
          availableLabels={labels}
          isLoading={loadingLabels}
          helperText="Select or create labels for the job"
          placeholderText="Select or create labels"
          onSearchChange={onSearchLabels}
          labelHelp={stepHelp.aapLabels}
        />
      )}
      {templateDetail.ask_verbosity_on_launch && <VerbosityField />}
      {templateDetail.ask_forks_on_launch && (
        <NumberInputField
          label="Forks"
          fieldId="aap-forks"
          name="forks"
          placeholder="0"
          min={0}
          labelHelp={stepHelp.aapForks}
        />
      )}
      {templateDetail.ask_job_slice_count_on_launch && (
        <NumberInputField
          label="Job slicing"
          fieldId="aap-jobSlicing"
          name="job_slice_count"
          placeholder="1"
          min={1}
          labelHelp={stepHelp.aapJobSliceCount}
        />
      )}
      {templateDetail.ask_diff_mode_on_launch && <DiffModeField />}
      {templateDetail.ask_instance_groups_on_launch && (
        <AAPResourceSelectField
          label="Instance groups"
          fieldId="aap-instanceGroups"
          nameField="instance_group"
          idField="instance_group_id"
          items={instanceGroups}
          isLoading={loadingInstanceGroups}
          helperText="Override default instance groups for the job"
          labelHelp={stepHelp.aapInstanceGroup}
          placeholderText="Use default instance groups"
          onSearchChange={onSearchInstanceGroups}
        />
      )}
      {templateDetail.ask_tags_on_launch && (
        <TagInputField
          label="Job tags"
          fieldId="aap-tags"
          name="tags"
          placeholder="tag1"
          helperText="Type a tag and press Enter or comma to add"
          labelHelp={stepHelp.aapTags}
        />
      )}
      {templateDetail.ask_skip_tags_on_launch && (
        <TagInputField
          label="Skip tags"
          fieldId="aap-skipTags"
          name="skip_tags"
          placeholder="tag1"
          helperText="Type a tag and press Enter or comma to add"
          labelHelp={stepHelp.aapSkipTags}
        />
      )}
      {templateDetail.ask_limit_on_launch && (
        <TextInputField label="Limit" fieldId="aap-limit" name="limit" labelHelp={stepHelp.aapLimit} />
      )}
      {templateDetail.ask_variables_on_launch && <ExtraVariablesField editorRef={extraVarsEditorRef} />}
    </>
  )
}

const noop = () => {}

export function PromptOnLaunchFields({
  extraVarsEditorRef,
  templateDetail,
  isLoadingDetail,
  inventories = [],
  loadingInventories = false,
  executionEnvironments = [],
  loadingExecutionEnvironments = false,
  credentials = [],
  loadingCredentials = false,
  instanceGroups = [],
  loadingInstanceGroups = false,
  labels = [],
  loadingLabels = false,
  onSearchInventories = noop,
  onSearchExecutionEnvironments = noop,
  onSearchCredentials = noop,
  onSearchInstanceGroups = noop,
  onSearchLabels = noop,
}: Readonly<PromptOnLaunchFieldsProps>) {
  if (!templateDetail || isLoadingDetail || !hasAnyPromptFlag(templateDetail)) {
    return null
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h4">Prompt on Launch</Title>
      </StackItem>
      <PromptOnLaunchFieldList
        templateDetail={templateDetail}
        inventories={inventories}
        loadingInventories={loadingInventories}
        executionEnvironments={executionEnvironments}
        loadingExecutionEnvironments={loadingExecutionEnvironments}
        credentials={credentials}
        loadingCredentials={loadingCredentials}
        instanceGroups={instanceGroups}
        loadingInstanceGroups={loadingInstanceGroups}
        labels={labels}
        loadingLabels={loadingLabels}
        extraVarsEditorRef={extraVarsEditorRef}
        onSearchInventories={onSearchInventories}
        onSearchExecutionEnvironments={onSearchExecutionEnvironments}
        onSearchCredentials={onSearchCredentials}
        onSearchInstanceGroups={onSearchInstanceGroups}
        onSearchLabels={onSearchLabels}
      />
    </Stack>
  )
}
