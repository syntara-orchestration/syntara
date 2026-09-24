import {
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextInput,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { ReactNode } from 'react'
import { use, useEffect, useMemo } from 'react'
import { Controller, FormProvider, useForm, useFormContext, useFormState, useWatch } from 'react-hook-form'

import { ExpandableCodeEditor } from '../components/ExpandableCodeEditor'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { mcpToolFormSchema, type MCPToolFormValues } from './mcpToolFormSchema'
import { McpServerSelect, McpToolNameSelect } from './McpToolSelects'
import { ActivityNameField } from './shared/ActivityNameField'
import { zodResolver } from './shared/formSchemaUtils'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'

export type { MCPToolFormValues }

type MCPToolNodeFormProps = {
  onSubmit: (data: MCPToolFormValues) => void
  initialData?: Partial<MCPToolFormValues>
  onHeaderContentChange?: (content: ReactNode | null) => void
  /** Scopes the integration query to this project. */
  projectId?: string
}

function FieldError({ message }: Readonly<{ message: string | undefined }>) {
  if (!message) return null
  return (
    <FormHelperText>
      <HelperText>
        <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
          {message}
        </HelperTextItem>
      </HelperText>
    </FormHelperText>
  )
}

function MCPToolFormFields({
  onHeaderContentChange,
  projectId,
}: Readonly<{ onHeaderContentChange?: (content: ReactNode | null) => void; projectId?: string }>) {
  const isVersionView = useIsVersionView()
  const { register, control, setValue } = useFormContext<MCPToolFormValues>()
  const { errors } = useFormState<MCPToolFormValues>()
  const integrationId = useWatch({ control, name: 'integration_id' })

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="mcp-tool-name" ariaLabel="Name" />,
    [register]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const parametersContent = (
    <Stack hasGutter>
      {!onHeaderContentChange && <ActivityNameField register={register} fieldId="mcp-tool-name" />}

      <StackItem>
        <FormGroup
          label="MCP server integration"
          labelHelp={nodeHelp.mcpToolIntegration}
          isRequired
          fieldId="mcp-tool-integration"
        >
          <Controller
            control={control}
            name="integration_id"
            render={({ field }) => (
              <McpServerSelect
                id="mcp-tool-integration"
                value={field.value}
                projectId={projectId}
                isDisabled={isVersionView}
                onChange={(integrationId) => {
                  field.onChange(integrationId)
                  // Tools are per-integration: clear a stale selection when the server changes.
                  setValue('tool_name', '', { shouldValidate: false })
                }}
              />
            )}
          />
          <FieldError message={errors.integration_id?.message} />
        </FormGroup>
      </StackItem>

      <StackItem>
        <FormGroup label="Tool" labelHelp={nodeHelp.mcpToolName} isRequired fieldId="mcp-tool-tool-name">
          <Controller
            control={control}
            name="tool_name"
            render={({ field }) => (
              <McpToolNameSelect
                id="mcp-tool-tool-name"
                integrationId={integrationId}
                value={field.value}
                isDisabled={isVersionView}
                onChange={field.onChange}
              />
            )}
          />
          <FieldError message={errors.tool_name?.message} />
        </FormGroup>
      </StackItem>

      <StackItem>
        <FormGroup label="Arguments" labelHelp={nodeHelp.mcpToolArguments} fieldId="mcp-tool-arguments">
          <Controller
            control={control}
            name="argumentsJson"
            render={({ field }) => (
              <ExpandableCodeEditor
                code={field.value ?? ''}
                onCodeChange={field.onChange}
                language="json"
                height="160px"
                modalTitle="Tool arguments"
                ariaLabel="Tool arguments JSON editor"
                isDarkTheme
                isReadOnly={isVersionView}
              />
            )}
          />
          <FormHelperText>
            <HelperText>
              <HelperTextItem {...(errors.argumentsJson && { icon: <RhUiErrorIcon />, variant: 'error' as const })}>
                {errors.argumentsJson?.message ?? 'JSON object passed to the tool, e.g. {"path": "/tmp"}'}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        </FormGroup>
      </StackItem>

      <StackItem>
        <FormGroup label="Timeout" labelHelp={nodeHelp.mcpToolTimeout} fieldId="mcp-tool-timeout">
          <Controller
            control={control}
            name="timeout_seconds"
            render={({ field }) => (
              <TextInput
                id="mcp-tool-timeout"
                type="number"
                min={1}
                max={600}
                aria-label="Timeout in seconds"
                value={field.value ?? ''}
                isDisabled={isVersionView}
                onChange={(_event, value) => field.onChange(value === '' ? undefined : Number(value))}
              />
            )}
          />
          <FieldError message={errors.timeout_seconds?.message} />
        </FormGroup>
      </StackItem>
    </Stack>
  )

  const settingsContent = <NodeSettingsForm supportsRetryPolicy={false} />

  return <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function MCPToolNodeForm(props: Readonly<MCPToolNodeFormProps>) {
  const defaultValues: MCPToolFormValues = {
    name: '',
    integration_id: '',
    tool_name: '',
    argumentsJson: '',
    ...props.initialData,
  }

  const methods = useForm<MCPToolFormValues>({
    resolver: zodResolver(mcpToolFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
    mode: 'onChange',
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, props.onSubmit)

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="mcp-tool-node-form" onSubmit={methods.handleSubmit(props.onSubmit)}>
        <MCPToolFormFields onHeaderContentChange={props.onHeaderContentChange} projectId={props.projectId} />
      </NodeFormContainer>
    </FormProvider>
  )
}
