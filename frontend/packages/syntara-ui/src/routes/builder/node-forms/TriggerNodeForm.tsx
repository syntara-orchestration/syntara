import {
  Alert,
  Content,
  ContentVariants,
  FormGroup,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
} from '@patternfly/react-core'
import { MissedSchedulePolicyEnum, ScheduleTypeEnum, TriggerTypeEnum, WEBHOOK_TRIGGER_TYPES } from '@syntara/contracts'
import type { ReactNode } from 'react'
import { useCallback, use, useEffect, useMemo, useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { FieldHelpPopover } from '../../../components/FieldHelpPopover'
import { ScheduleBuilderFields } from '../../../components/forms/ScheduleBuilderFields'
import {
  CRON_EXPRESSION_HELP,
  EXECUTION_CONFLICT_HELP,
  SCHEDULE_EXPRESSION_HELP,
} from '../../../components/forms/scheduleHelpText'
import { SynForm } from '../../../components/forms/SynForm'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynTextField } from '../../../components/forms/SynTextField'
import { SynSelect } from '../../../components/SynSelect'
import { useSynForm } from '../../../hooks/useSynForm'
import { getDefaultRepeatingInterval } from '../../../utils/triggerFormatting'
import { generateWebhookPath } from '../../../utils/webhookPath'
import { NodeEditorAutoSubmitContext, useRegisterAutoSubmit } from '../hooks/useNodeEditorAutoSubmit'
import { useIsVersionView } from '../VersionViewContext'

import { EdaFields } from './EdaTriggerFields'
import { ManualTriggerFields } from './ManualTriggerFields'
import { ActivityNameField } from './shared/ActivityNameField'
import { NodeFormContainer } from './shared/NodeFormContainer'
import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { NodeFormTabsLayout } from './shared/NodeFormTabsLayout'
import { normalizeWebhookPath, triggerFormSchema, type TriggerFormData } from './triggerFormSchema'
import { WebhookFields } from './WebhookTriggerFields'

const executionConflictLabelHelp = (
  <FieldHelpPopover headerContent="Execution conflict policy" helpText={EXECUTION_CONFLICT_HELP} />
)
const scheduleExpressionLabelHelp = (
  <FieldHelpPopover headerContent="Schedule expression" helpText={SCHEDULE_EXPRESSION_HELP} />
)
const cronExpressionLabelHelp = <FieldHelpPopover headerContent="Cron expression" helpText={CRON_EXPRESSION_HELP} />

export type { TriggerFormData }

function resolveBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch {
    return 'UTC'
  }
}

function buildTriggerFormDefaults(initialData?: Partial<TriggerFormData>): TriggerFormData {
  const values: TriggerFormData = {
    name: '',
    triggerType: initialData?.triggerType ?? TriggerTypeEnum.MANUAL_TRIGGER,
    scheduleType: ScheduleTypeEnum.INTERVAL,
    interval: '',
    cron: '',
    timezone: resolveBrowserTimezone(),
    missedSchedulePolicy: MissedSchedulePolicyEnum.SKIP,
    inputSchema: '',
    webhookPath: '',
    ...initialData,
  }

  if (WEBHOOK_TRIGGER_TYPES.has(values.triggerType) && !values.webhookPath) {
    values.webhookPath = generateWebhookPath()
  }

  if (
    values.triggerType === TriggerTypeEnum.SCHEDULED &&
    values.scheduleType === ScheduleTypeEnum.INTERVAL &&
    !values.interval?.trim()
  ) {
    values.interval = getDefaultRepeatingInterval(values.timezone ?? 'UTC')
  }

  return values
}

type TriggerNodeFormProps = Readonly<{
  onSubmit: (data: TriggerFormData) => void
  initialData?: Partial<TriggerFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}>

// ── Execution conflict policy options ────────────────────────────────────

const conflictPolicyOptions = [
  {
    value: MissedSchedulePolicyEnum.SKIP,
    label: 'Skip (Default)',
    description:
      'If the previous run is still in progress, the new run is ignored. Only one instance of the workflow runs at a time.',
  },
  {
    value: MissedSchedulePolicyEnum.BUFFER_ONE,
    label: 'Buffer one',
    description:
      'If runs were skipped because the previous one was still in progress, the system will queue one catch-up execution and then resume the normal schedule.',
  },
  {
    value: MissedSchedulePolicyEnum.BUFFER_ALL,
    label: 'Buffer all',
    description: 'Every scheduled run is queued, even if previous runs are still in progress.',
  },
  {
    value: MissedSchedulePolicyEnum.ALLOW_ALL,
    label: 'Allow all',
    description:
      'Start every scheduled run immediately, even if previous runs are still in progress. Multiple runs may execute concurrently.',
  },
  {
    value: MissedSchedulePolicyEnum.CANCEL_OTHER,
    label: 'Cancel other',
    description: 'Cancel the currently in-progress run and start the new one. Only the latest scheduled run executes.',
  },
]

// ── Sub-components (module-scoped per S6478) ─────────────────────────────

function ExecutionConflictPolicyField({
  value,
  onChange,
  isDisabled,
}: Readonly<{
  value: string
  onChange: (val: string) => void
  isDisabled: boolean
}>) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = conflictPolicyOptions.find((o) => o.value === value)?.label ?? 'Skip'

  const handleSelect = useCallback(
    (_event: React.MouseEvent | undefined, val: string | number | undefined) => {
      if (val === undefined) return
      onChange(String(val))
      setIsOpen(false)
    },
    [onChange]
  )

  const renderToggle = useCallback(
    (toggleRef: React.Ref<MenuToggleElement>) => (
      <MenuToggle
        ref={toggleRef}
        onClick={() => setIsOpen((prev) => !prev)}
        isExpanded={isOpen}
        isFullWidth
        isDisabled={isDisabled}
        aria-label="Execution conflict policy"
      >
        {selectedLabel}
      </MenuToggle>
    ),
    [isOpen, selectedLabel, isDisabled]
  )

  return (
    <StackItem>
      <FormGroup
        label="Execution conflict policy"
        labelHelp={executionConflictLabelHelp}
        fieldId="execution-conflict-policy"
        isRequired
      >
        <SynSelect
          id="execution-conflict-policy"
          isOpen={isOpen}
          selected={value}
          onSelect={handleSelect}
          onOpenChange={setIsOpen}
          shouldFocusToggleOnSelect
          toggle={renderToggle}
        >
          <SelectList aria-label="Execution conflict policy options">
            {conflictPolicyOptions.map((option) => (
              <SelectOption key={option.value} value={option.value} description={option.description}>
                {option.label}
              </SelectOption>
            ))}
          </SelectList>
        </SynSelect>
      </FormGroup>
    </StackItem>
  )
}

function ScheduleTypeSelect({
  value = ScheduleTypeEnum.INTERVAL,
  onChange,
  isDisabled,
}: {
  value?: string
  onChange: (value: string) => void
  isDisabled?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <SynSelect
      id="schedule-expression"
      isOpen={isOpen}
      selected={value}
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
          aria-label="Schedule expression"
        >
          {value === ScheduleTypeEnum.INTERVAL ? 'Visual schedule builder' : 'Custom cron expression'}
        </MenuToggle>
      )}
    >
      <SelectList>
        <SelectOption value={ScheduleTypeEnum.INTERVAL}>Visual schedule builder</SelectOption>
        <SelectOption value={ScheduleTypeEnum.CRON}>Custom cron expression</SelectOption>
      </SelectList>
    </SynSelect>
  )
}

function ScheduleIntervalFields({
  intervalError,
  isEndDateError,
}: Readonly<{
  intervalError?: { message?: string }
  isEndDateError: boolean
}>) {
  const timezone = useWatch<TriggerFormData, 'timezone'>({ name: 'timezone' })
  const { setValue } = useFormContext<TriggerFormData>()

  return (
    <SynFormField name="interval" label="" hideFormGroupLabel hideFooter>
      {({ field }) => (
        <ScheduleBuilderFields
          value={typeof field.value === 'string' ? field.value : ''}
          onChange={field.onChange}
          timezone={timezone ?? 'UTC'}
          onTimezoneChange={(tz) => setValue('timezone', tz, { shouldDirty: true })}
          required
          error={!!intervalError && !isEndDateError}
          errorMessage={intervalError?.message}
        />
      )}
    </SynFormField>
  )
}

// ── Main form fields ─────────────────────────────────────────────────────

function TriggerFormFields({
  onHeaderContentChange,
  validationErrors,
}: Readonly<{
  onHeaderContentChange?: (content: ReactNode | null) => void
  validationErrors?: {
    interval?: { message?: string }
    cron?: { message?: string }
    inputSchema?: { message?: string }
    webhookPath?: { message?: string }
  }
}>) {
  const isVersionView = useIsVersionView()
  const {
    control,
    register,
    formState: { errors: contextErrors },
  } = useFormContext<TriggerFormData>()
  const errors = validationErrors ?? contextErrors
  const triggerType = useWatch({ control, name: 'triggerType' })
  const scheduleType = useWatch({ control, name: 'scheduleType' })

  const isEndDateError = Boolean(errors.interval?.message?.toLowerCase().includes('end date'))

  useEffect(() => {
    if (!errors.interval) return
    const target = isEndDateError ? 'schedule-end-date' : 'schedule-start-date'
    document.getElementById(target)?.focus()
  }, [errors.interval, isEndDateError])

  useEffect(() => {
    if (errors.cron) document.getElementById('cron-expression')?.focus()
  }, [errors.cron])

  const nameField = useMemo(
    () => (
      <ActivityNameField control={control} fieldId="trigger-name" placeholder="Enter trigger name" ariaLabel="Name" />
    ),
    [control]
  )

  useEffect(() => {
    onHeaderContentChange?.(nameField)
    return () => {
      onHeaderContentChange?.(null)
    }
  }, [nameField, onHeaderContentChange])

  const parametersContent = (
    <Stack hasGutter>
      <input type="hidden" {...register('triggerType')} />

      {triggerType === TriggerTypeEnum.MANUAL_TRIGGER && (
        <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
          <ManualTriggerFields errors={errors} />
        </fieldset>
      )}

      {triggerType === TriggerTypeEnum.SCHEDULED && (
        <>
          <StackItem>
            <Alert variant="info" isInline title="Schedule activation" component="h4">
              <Content component={ContentVariants.p}>
                This schedule will only take effect once the workflow is published. Changes to the schedule are applied
                on the next publish.
              </Content>
            </Alert>
          </StackItem>

          <StackItem>
            <SynFormField
              name="scheduleType"
              label="Schedule expression"
              labelHelp={scheduleExpressionLabelHelp}
              fieldId="schedule-expression"
              isRequired
            >
              {({ field }) => (
                <ScheduleTypeSelect
                  value={field.value as TriggerFormData['scheduleType']}
                  onChange={field.onChange}
                  isDisabled={isVersionView}
                />
              )}
            </SynFormField>
          </StackItem>

          {scheduleType === ScheduleTypeEnum.INTERVAL && (
            <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
              <Stack hasGutter>
                <StackItem>
                  <ScheduleIntervalFields intervalError={errors.interval} isEndDateError={isEndDateError} />
                </StackItem>

                <SynFormField name="missedSchedulePolicy" label="" hideFormGroupLabel hideFooter>
                  {({ field }) => (
                    <ExecutionConflictPolicyField
                      value={(field.value as TriggerFormData['missedSchedulePolicy']) ?? MissedSchedulePolicyEnum.SKIP}
                      onChange={field.onChange}
                      isDisabled={isVersionView}
                    />
                  )}
                </SynFormField>
              </Stack>
            </fieldset>
          )}

          {scheduleType === ScheduleTypeEnum.CRON && (
            <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
              <Stack hasGutter>
                <StackItem>
                  <SynTextField
                    name="cron"
                    label="Cron expression"
                    ariaLabel="Cron expression"
                    labelHelp={cronExpressionLabelHelp}
                    fieldId="cron-expression"
                    isRequired
                    placeholder="0 9 * * 1"
                    hint="Format: [Minute] [Hour] [Day of the Month] [Month] [Day of the Week]"
                    isDisabled={isVersionView}
                  />
                </StackItem>

                <SynFormField name="missedSchedulePolicy" label="" hideFormGroupLabel hideFooter>
                  {({ field }) => (
                    <ExecutionConflictPolicyField
                      value={(field.value as TriggerFormData['missedSchedulePolicy']) ?? MissedSchedulePolicyEnum.SKIP}
                      onChange={field.onChange}
                      isDisabled={isVersionView}
                    />
                  )}
                </SynFormField>
              </Stack>
            </fieldset>
          )}
        </>
      )}

      {triggerType === TriggerTypeEnum.WEBHOOK_TRIGGER && (
        <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
          <Stack hasGutter>
            <WebhookFields />
          </Stack>
        </fieldset>
      )}

      {triggerType === TriggerTypeEnum.EDA_TRIGGER && (
        <fieldset disabled={isVersionView} className={nodeFormStyles.disabledFieldset}>
          <Stack hasGutter>
            <EdaFields />
          </Stack>
        </fieldset>
      )}
    </Stack>
  )

  return <NodeFormTabsLayout parametersContent={parametersContent} hideSettingsTab />
}

export function TriggerNodeForm(props: TriggerNodeFormProps) {
  const [defaultValues] = useState<TriggerFormData>(() => buildTriggerFormDefaults(props.initialData))

  const form = useSynForm({
    schema: triggerFormSchema,
    defaultValues,
  })

  const {
    formState: { errors },
  } = form

  const handleSubmit = (data: TriggerFormData) => {
    const isManual = data.triggerType === TriggerTypeEnum.MANUAL_TRIGGER
    const isScheduled = data.triggerType === TriggerTypeEnum.SCHEDULED
    const isWebhookStyle = WEBHOOK_TRIGGER_TYPES.has(data.triggerType)

    const cleanedData: TriggerFormData = {
      name: data.name,
      triggerType: data.triggerType,
      inputSchema: isManual || isWebhookStyle ? data.inputSchema : undefined,
      scheduleType: isScheduled ? data.scheduleType : undefined,
      interval: isScheduled && data.scheduleType === ScheduleTypeEnum.INTERVAL ? data.interval : undefined,
      cron: isScheduled && data.scheduleType === ScheduleTypeEnum.CRON ? data.cron : undefined,
      timezone: isScheduled ? data.timezone : undefined,
      missedSchedulePolicy: isScheduled ? data.missedSchedulePolicy : undefined,
      webhookPath: isWebhookStyle ? normalizeWebhookPath(data.webhookPath ?? '') : undefined,
      authorizedServiceAccountIds: isWebhookStyle ? data.authorizedServiceAccountIds : undefined,
    }
    props.onSubmit(cleanedData)
  }

  const autoSubmitRef = use(NodeEditorAutoSubmitContext)
  useRegisterAutoSubmit(autoSubmitRef, form, handleSubmit)

  return (
    <NodeFormContainer formId="trigger-node-form" onSubmit={form.handleSubmit(handleSubmit)}>
      <SynForm form={form}>
        <TriggerFormFields onHeaderContentChange={props.onHeaderContentChange} validationErrors={errors} />
      </SynForm>
    </NodeFormContainer>
  )
}
