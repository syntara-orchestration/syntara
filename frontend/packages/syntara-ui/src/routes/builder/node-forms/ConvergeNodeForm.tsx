import {
  Alert,
  Content,
  ContentVariants,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  TextInput,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import React, { type ReactNode, use, useEffect, useMemo, useState } from 'react'
import { Controller, FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form'

import { SynSelect } from '../../../components/SynSelect'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'
import { formatDuration } from '../utils/timeUtils'
import { useIsVersionView } from '../VersionViewContext'

import { convergeFormSchema, type ConvergeFormData, type ConvergeStrategy } from './convergeFormSchema'
import { ActivityNameField } from './shared/ActivityNameField'
import { ContinueWhenCriteriaHelp } from './shared/ContinueWhenCriteriaHelp'
import { DurationInput } from './shared/DurationInput'
import { zodResolver } from './shared/formSchemaUtils'
import { nodeHelp } from './shared/nodeFieldHelp'
import { NodeFormContainer } from './shared/NodeFormContainer'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { NodeSettingsForm } from './shared/NodeSettingsForm'
import { RequiredBranchCountHelp } from './shared/RequiredBranchCountHelp'

export type { ConvergeFormData, ConvergeStrategy }

/** Options for "Continue when criteria" dropdown */
const CONTINUE_WHEN_CRITERIA_OPTIONS: Array<{ label: string; value: ConvergeStrategy }> = [
  { label: 'All branches reach this step', value: 'all' },
  { label: 'Any branches reach this step', value: 'any' },
]

function ContinueWhenSelect({
  value,
  onChange,
  isDisabled,
  validated,
}: {
  value: string
  onChange: (value: string) => void
  isDisabled?: boolean
  validated?: 'error' | 'default'
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = CONTINUE_WHEN_CRITERIA_OPTIONS.find((o) => o.value === value)?.label
  return (
    <SynSelect
      id="converge-strategy"
      isOpen={isOpen}
      selected={value || undefined}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={setIsOpen}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isDisabled={isDisabled}
          isPlaceholder={!value}
          status={validated === 'error' ? 'danger' : undefined}
          aria-label="Continue when criteria"
        >
          {selectedLabel ?? 'Select continue when criteria'}
        </MenuToggle>
      )}
    >
      <SelectList>
        {CONTINUE_WHEN_CRITERIA_OPTIONS.map((o) => (
          <SelectOption key={o.value} value={o.value}>
            {o.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

type ConvergeNodeFormProps = {
  onSubmit: (data: ConvergeFormData) => void
  initialData?: Partial<ConvergeFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}

function ConvergeFormFields({
  onHeaderContentChange,
  validationErrors,
}: {
  onHeaderContentChange?: (content: ReactNode | null) => void
  validationErrors?: {
    strategy?: { message?: string }
    requiredPathCount?: { message?: string }
  }
}) {
  const {
    register,
    control,
    setValue,
    formState: { errors: contextErrors },
  } = useFormContext<ConvergeFormData>()
  const isVersionView = useIsVersionView()
  const errors = validationErrors ?? contextErrors
  const strategy = useWatch({ control, name: 'strategy' })
  const waitDuration = useWatch({ control, name: 'wait_duration' })
  const { defaults } = useWorkflowEngineDefaults()
  const convergeWaitDurationDefault = defaults?.convergeWaitDuration ?? null

  useEffect(() => {
    if (errors.strategy) document.getElementById('converge-strategy')?.focus()
  }, [errors.strategy])

  const nameField = useMemo(
    () => <ActivityNameField register={register} fieldId="converge-name" ariaLabel="Name" />,
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
      {!onHeaderContentChange && <ActivityNameField register={register} fieldId="converge-name" />}

      <StackItem>
        <Alert
          variant="info"
          isInline
          isExpandable
          component="h4"
          title="Converge waits for parallel branches to finish executing before continuing"
        >
          <Content component={ContentVariants.p}>
            Use this step when multiple branches run at the same time and the workflow should wait before continuing.
            For example, after fanning out from one step into tasks that execute in parallel.
          </Content>
          <Content component={ContentVariants.p}>
            You do not need Converge after Conditional, Switch, or Approval steps. Those steps route execution to one
            branch only, so there are no concurrent paths to synchronize. Connect each branch directly to the next step.
          </Content>
        </Alert>
      </StackItem>

      <StackItem>
        <FormGroup
          label="Continue when criteria"
          labelHelp={<ContinueWhenCriteriaHelp />}
          isRequired
          fieldId="converge-strategy"
        >
          <Controller
            control={control}
            name="strategy"
            render={({ field }) => (
              <ContinueWhenSelect
                value={field.value ?? ''}
                onChange={field.onChange}
                isDisabled={isVersionView}
                validated={errors.strategy ? 'error' : 'default'}
              />
            )}
          />
          {errors.strategy && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                  {errors.strategy.message}
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
        </FormGroup>
      </StackItem>

      {strategy === 'any' && (
        <StackItem>
          <FormGroup
            label="Required number of branches before continuing"
            labelHelp={<RequiredBranchCountHelp />}
            isRequired
            fieldId="converge-requiredPathCount"
          >
            <TextInput
              {...register('requiredPathCount', { valueAsNumber: true })}
              id="converge-requiredPathCount"
              type="number"
              min={1}
              isDisabled={isVersionView}
            />
            {errors.requiredPathCount && (
              <FormHelperText>
                <HelperText>
                  <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                    {errors.requiredPathCount.message}
                  </HelperTextItem>
                </HelperText>
              </FormHelperText>
            )}
          </FormGroup>
        </StackItem>
      )}

      <StackItem>
        <FormGroup
          label="Wait duration"
          labelHelp={nodeHelp.convergeWaitDuration}
          fieldId="converge-wait-duration-days"
        >
          <Stack hasGutter>
            <StackItem>
              <DurationInput
                value={waitDuration}
                onChange={(val) => setValue('wait_duration', val, { shouldDirty: true })}
                idPrefix="converge-wait-duration"
                isDisabled={isVersionView}
              />
            </StackItem>
            <StackItem>
              <HelperText>
                <HelperTextItem>
                  {convergeWaitDurationDefault !== null
                    ? `How long to wait for branches to arrive before timing out. Falls back to system default (${formatDuration(convergeWaitDurationDefault)}) if not set.`
                    : 'How long to wait for branches to arrive before timing out. Falls back to system default if not set.'}
                </HelperTextItem>
              </HelperText>
            </StackItem>
          </Stack>
        </FormGroup>
      </StackItem>
    </Stack>
  )

  const settingsContent = (
    <NodeSettingsForm
      supportsTimeout={false}
      supportsRetryPolicy={false}
      continueOnFailureHelp={
        'When “Continue on failure” is selected and the wait duration expires before all required branches arrive, the workflow proceeds with whichever branches have completed. Incomplete branches are marked skipped.'
      }
    />
  )

  return <NodeFormTabsLayout parametersContent={parametersContent} settingsContent={settingsContent} />
}

export function ConvergeNodeForm(props: ConvergeNodeFormProps) {
  const defaultValues: ConvergeFormData = {
    name: '',
    strategy: 'all',
    requiredPathCount: 1,
    settings: {},
    ...props.initialData,
  }

  const handleSubmit = (data: ConvergeFormData) => {
    const cleanedData: ConvergeFormData = {
      name: data.name,
      strategy: data.strategy,
      wait_duration: data.wait_duration,
      settings: data.settings,
      requiredPathCount: data.strategy === 'any' ? data.requiredPathCount : undefined,
    }

    props.onSubmit(cleanedData)
  }

  const methods = useForm<ConvergeFormData>({
    resolver: zodResolver(convergeFormSchema, undefined, { mode: 'sync' }),
    defaultValues,
  })

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, methods, handleSubmit)

  const {
    formState: { errors },
  } = methods

  return (
    <FormProvider {...methods}>
      <NodeFormContainer formId="converge-node-form" onSubmit={methods.handleSubmit(handleSubmit)}>
        <ConvergeFormFields onHeaderContentChange={props.onHeaderContentChange} validationErrors={errors} />
      </NodeFormContainer>
    </FormProvider>
  )
}
