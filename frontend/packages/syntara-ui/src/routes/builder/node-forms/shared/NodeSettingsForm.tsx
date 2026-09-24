import {
  FormGroup,
  FormSection,
  HelperText,
  HelperTextItem,
  MenuToggle,
  SelectList,
  SelectOption,
  Stack,
  StackItem,
  Switch,
  TextInput,
} from '@patternfly/react-core'
import { useState } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { SynSelect } from '../../../../components/SynSelect'
import type { TimeoutNodeType } from '../../hooks/useWorkflowEngineDefaults'
import { useWorkflowEngineDefaults } from '../../hooks/useWorkflowEngineDefaults'
import { useIsVersionView } from '../../VersionViewContext'

import { DurationInput } from './DurationInput'
import { nodeHelp } from './nodeFieldHelp'
import type { NodeSettingsFormData } from './nodeSettingsSchema'

type FormWithSettings = { settings: NodeSettingsFormData }

type NodeSettingsFormProps = {
  /** How to render the timeout field. 'seconds' = plain number input, 'duration' = days/hours/minutes/seconds picker. */
  timeoutFormat?: 'seconds' | 'duration'
  /** When false, the timeout field is not rendered. Default: true. */
  supportsTimeout?: boolean
  /** When false, the continue_on_failure toggle is not rendered. Default: true. */
  supportsContinueOnFailure?: boolean
  /** When false, the retry policy section is not rendered. Default: true. */
  supportsRetryPolicy?: boolean
  /** Additional help text shown under the continue_on_failure dropdown. */
  continueOnFailureHelp?: string
  /** When set, hides the inner "On failure behavior" label (section title only). */
  continueOnFailureHideFieldLabel?: boolean
  /** Node type used to select the matching system timeout default. */
  timeoutNodeType?: TimeoutNodeType
  /** Overrides system default seconds for timeout placeholder/help (e.g. expected-duration UI). */
  timeoutDefaultSeconds?: number
  /** Custom timeout section title. Omit for default; pass empty string for no section title. */
  timeoutSectionTitle?: string
  /** Custom timeout field label (seconds input mode). */
  timeoutLabel?: string
  /** Custom helper text under the timeout field. */
  timeoutHelp?: string
}

function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return [d > 0 && `${d}d`, h > 0 && `${h}h`, m > 0 && `${m}m`].filter(Boolean).join(' ')
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

// ── Sub-sections (module-scoped to avoid Sonar S6478) ──────────────────────

const COF_OPTIONS = [
  {
    value: 'default' as const,
    label: 'System default',
    description: (systemDefault: string) =>
      `Uses the system-wide setting configured by an administrator${systemDefault}.`,
  },
  {
    value: 'on' as const,
    label: 'Continue on failure',
    description: () => 'Downstream nodes continue executing even if this node fails.',
  },
  {
    value: 'off' as const,
    label: 'Stop workflow or branch on failure',
    description: () => 'The workflow (or current branch) stops at this node if it fails.',
  },
] as const

type CofValue = 'default' | 'on' | 'off'

function cofValueFromBool(v: boolean | undefined | null): CofValue {
  if (v === true) return 'on'
  if (v === false) return 'off'
  return 'default'
}

function cofValueToBool(v: CofValue): boolean | undefined {
  if (v === 'on') return true
  if (v === 'off') return false
  return undefined
}

type CofSectionProps = {
  continueOnFailure: boolean | undefined | null
  cofDefaultLabel: string
  continueOnFailureHelp?: string
  hideFieldLabel?: boolean
  setValue: (name: 'settings.continue_on_failure', value: boolean | undefined) => void
  isDisabled?: boolean
}

function ContinueOnFailureSection({
  continueOnFailure,
  cofDefaultLabel,
  continueOnFailureHelp,
  hideFieldLabel,
  setValue,
  isDisabled,
}: CofSectionProps) {
  const [isOpen, setIsOpen] = useState(false)
  const selected = cofValueFromBool(continueOnFailure)
  const selectedLabel = COF_OPTIONS.find((o) => o.value === selected)?.label ?? 'System default'

  function handleSelect(_event: React.MouseEvent | undefined, value: string | number | undefined) {
    setValue('settings.continue_on_failure', cofValueToBool(value as CofValue))
    setIsOpen(false)
  }

  return (
    <FormSection title="On failure">
      <Stack hasGutter>
        <StackItem>
          <FormGroup
            label={hideFieldLabel ? undefined : 'On failure behavior'}
            labelHelp={hideFieldLabel ? undefined : nodeHelp.onFailureBehavior}
            fieldId="node-settings-cof"
          >
            <SynSelect
              id="node-settings-cof"
              isOpen={isOpen}
              selected={selected}
              onSelect={handleSelect}
              onOpenChange={setIsOpen}
              shouldFocusToggleOnSelect
              toggle={(ref) => (
                <MenuToggle
                  ref={ref}
                  onClick={() => setIsOpen((o) => !o)}
                  isExpanded={isOpen}
                  isFullWidth
                  isDisabled={isDisabled}
                  aria-label="On failure behavior"
                >
                  {selectedLabel}
                </MenuToggle>
              )}
            >
              <SelectList>
                {COF_OPTIONS.map((opt) => (
                  <SelectOption key={opt.value} value={opt.value} description={opt.description(cofDefaultLabel)}>
                    {opt.label}
                  </SelectOption>
                ))}
              </SelectList>
            </SynSelect>
          </FormGroup>
        </StackItem>
        {continueOnFailureHelp && (
          <StackItem>
            <HelperText>
              <HelperTextItem>{continueOnFailureHelp}</HelperTextItem>
            </HelperText>
          </StackItem>
        )}
      </Stack>
    </FormSection>
  )
}

type TimeoutSectionProps = {
  timeoutFormat: 'seconds' | 'duration'
  timeoutDefault: number | null
  timeoutPlaceholder: string
  sectionTitle?: string
  fieldLabel?: string
  helperText?: string
  control: ReturnType<typeof useFormContext<FormWithSettings>>['control']
  register: ReturnType<typeof useFormContext<FormWithSettings>>['register']
  isDisabled?: boolean
}

function TimeoutSection({
  timeoutFormat,
  timeoutDefault,
  timeoutPlaceholder,
  sectionTitle,
  fieldLabel,
  helperText,
  control,
  register,
  isDisabled,
}: TimeoutSectionProps) {
  const durationHelp =
    helperText ??
    (timeoutDefault !== null
      ? `How long to wait before timing out. System default: ${formatSeconds(timeoutDefault)}.`
      : 'How long to wait before timing out. Falls back to system default if not set.')
  const secondsSectionTitle = sectionTitle ?? 'Timeout (seconds)'
  const secondsFieldLabel = fieldLabel ?? 'Timeout (seconds)'

  if (timeoutFormat === 'duration') {
    return (
      <FormSection title="Timeout">
        <Stack hasGutter>
          <StackItem>
            <FormGroup label="Timeout" labelHelp={nodeHelp.timeout} fieldId="node-settings-timeout">
              <Controller
                control={control}
                name="settings.timeout"
                render={({ field }) => (
                  <DurationInput
                    value={field.value}
                    onChange={field.onChange}
                    idPrefix="node-settings-timeout"
                    isDisabled={isDisabled}
                  />
                )}
              />
            </FormGroup>
          </StackItem>
          <StackItem>
            <HelperText>
              <HelperTextItem>{durationHelp}</HelperTextItem>
            </HelperText>
          </StackItem>
        </Stack>
      </FormSection>
    )
  }

  const secondsField = (
    <Stack hasGutter>
      <StackItem>
        <FormGroup
          label={secondsFieldLabel}
          labelHelp={helperText ? undefined : nodeHelp.timeout}
          fieldId="node-settings-timeout-seconds"
        >
          <TextInput
            {...register('settings.timeout', { setValueAs: (v) => (v === '' || v === null ? undefined : Number(v)) })}
            id="node-settings-timeout-seconds"
            aria-label={secondsFieldLabel}
            type="number"
            min={1}
            placeholder={timeoutPlaceholder}
            isDisabled={isDisabled}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <HelperText>
          <HelperTextItem>{durationHelp}</HelperTextItem>
        </HelperText>
      </StackItem>
    </Stack>
  )

  if (sectionTitle === '') {
    return secondsField
  }

  return <FormSection title={secondsSectionTitle}>{secondsField}</FormSection>
}

type RetryFieldsProps = {
  register: ReturnType<typeof useFormContext<FormWithSettings>>['register']
  retryDefaults: {
    maxRetries: number | null
    initialInterval: number | null
    maxInterval: number | null
    backoffCoefficient: number | null
  } | null
  isDisabled?: boolean
}

function retryPlaceholder(val: number | null | undefined, fallback: string): string {
  return val !== null && val !== undefined ? `${String(val)} — system default` : fallback
}

function RetryPolicyFields({ register, retryDefaults, isDisabled }: RetryFieldsProps) {
  return (
    <>
      <StackItem>
        <FormGroup label="Max retries" labelHelp={nodeHelp.maxRetries} fieldId="node-settings-max-retries">
          <TextInput
            {...register('settings.retry_policy.max_retries', { valueAsNumber: true })}
            id="node-settings-max-retries"
            type="number"
            min={0}
            placeholder={retryPlaceholder(retryDefaults?.maxRetries, '0 = no retry')}
            isDisabled={isDisabled}
          />
        </FormGroup>
        <HelperText>
          <HelperTextItem>Number of retries after the initial attempt. 0 = explicitly no retry.</HelperTextItem>
        </HelperText>
      </StackItem>
      <StackItem>
        <FormGroup
          label="Initial interval (seconds)"
          labelHelp={nodeHelp.initialInterval}
          fieldId="node-settings-initial-interval"
        >
          <TextInput
            {...register('settings.retry_policy.initial_interval', {
              setValueAs: (v) => (v === '' || v === null ? undefined : Number(v)),
            })}
            id="node-settings-initial-interval"
            type="number"
            min={1}
            placeholder={retryPlaceholder(retryDefaults?.initialInterval, 'System default')}
            isDisabled={isDisabled}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup label="Max interval (seconds)" labelHelp={nodeHelp.maxInterval} fieldId="node-settings-max-interval">
          <TextInput
            {...register('settings.retry_policy.max_interval', {
              setValueAs: (v) => (v === '' || v === null ? undefined : Number(v)),
            })}
            id="node-settings-max-interval"
            type="number"
            min={1}
            placeholder={retryPlaceholder(retryDefaults?.maxInterval, 'System default')}
            isDisabled={isDisabled}
          />
        </FormGroup>
      </StackItem>
      <StackItem>
        <FormGroup
          label="Backoff coefficient"
          labelHelp={nodeHelp.backoffCoefficient}
          fieldId="node-settings-backoff-coefficient"
        >
          <TextInput
            {...register('settings.retry_policy.backoff_coefficient', {
              setValueAs: (v) => (v === '' || v === null ? undefined : Number(v)),
            })}
            id="node-settings-backoff-coefficient"
            type="number"
            min={1}
            step={0.1}
            placeholder={retryPlaceholder(retryDefaults?.backoffCoefficient, 'System default')}
            isDisabled={isDisabled}
          />
        </FormGroup>
      </StackItem>
    </>
  )
}

function getCofDefaultLabel(cofDefault: boolean | null): string {
  if (cofDefault === null) return ''
  if (cofDefault) return ' (system default: continue on failure)'
  return ' (system default: stop on failure)'
}

function resolveTimeoutDefaultSeconds(
  timeoutDefaultSeconds: number | undefined,
  timeoutNodeType: TimeoutNodeType | undefined,
  defaults: ReturnType<typeof useWorkflowEngineDefaults>['defaults']
): number | null {
  if (timeoutDefaultSeconds !== undefined) {
    return timeoutDefaultSeconds
  }
  if (!timeoutNodeType) {
    return null
  }
  return defaults?.timeoutSeconds[timeoutNodeType] ?? null
}

type NodeSettingsFormSectionsProps = NodeSettingsFormProps & {
  isVersionView: boolean
  control: ReturnType<typeof useFormContext<FormWithSettings>>['control']
  register: ReturnType<typeof useFormContext<FormWithSettings>>['register']
  setValue: ReturnType<typeof useFormContext<FormWithSettings>>['setValue']
  continueOnFailure: boolean | undefined | null
  overrideRetry: boolean
  cofDefaultLabel: string
  timeoutDefault: number | null
  timeoutPlaceholder: string
  retryDefaults: RetryFieldsProps['retryDefaults']
}

function NodeSettingsFormSections({
  timeoutFormat = 'seconds',
  supportsTimeout = true,
  supportsContinueOnFailure = true,
  supportsRetryPolicy = true,
  continueOnFailureHelp,
  continueOnFailureHideFieldLabel = false,
  timeoutSectionTitle,
  timeoutLabel,
  timeoutHelp,
  isVersionView,
  control,
  register,
  setValue,
  continueOnFailure,
  overrideRetry,
  cofDefaultLabel,
  timeoutDefault,
  timeoutPlaceholder,
  retryDefaults,
}: NodeSettingsFormSectionsProps) {
  function handleRetryOverrideToggle(_event: React.FormEvent<HTMLInputElement>, checked: boolean) {
    if (checked) {
      setValue('settings.retry_policy', {})
    } else {
      setValue('settings.retry_policy', undefined)
    }
  }

  const retryHelp = retryDefaults
    ? `When disabled, the system default retry policy applies (${String(retryDefaults.maxRetries ?? '?')} retries, ${String(retryDefaults.initialInterval ?? '?')}s initial interval).`
    : 'When disabled, the system default retry policy applies.'

  return (
    <Stack hasGutter>
      {supportsContinueOnFailure && (
        <StackItem>
          <ContinueOnFailureSection
            continueOnFailure={continueOnFailure}
            cofDefaultLabel={cofDefaultLabel}
            continueOnFailureHelp={continueOnFailureHelp}
            hideFieldLabel={continueOnFailureHideFieldLabel}
            setValue={setValue}
            isDisabled={isVersionView}
          />
        </StackItem>
      )}

      {supportsTimeout && (
        <StackItem>
          <TimeoutSection
            timeoutFormat={timeoutFormat}
            timeoutDefault={timeoutDefault}
            timeoutPlaceholder={timeoutPlaceholder}
            sectionTitle={timeoutSectionTitle}
            fieldLabel={timeoutLabel}
            helperText={timeoutHelp}
            control={control}
            register={register}
            isDisabled={isVersionView}
          />
        </StackItem>
      )}

      {supportsRetryPolicy && (
        <StackItem>
          <FormSection title="Retry policy">
            <Stack hasGutter>
              <StackItem>
                <FormGroup
                  label="Override retry policy"
                  labelHelp={nodeHelp.retryToggle}
                  fieldId="node-settings-retry-override"
                >
                  <Switch
                    id="node-settings-retry-override"
                    aria-label="Override retry policy"
                    isChecked={overrideRetry}
                    onChange={handleRetryOverrideToggle}
                    isDisabled={isVersionView}
                  />
                </FormGroup>
                <HelperText>
                  <HelperTextItem>{retryHelp}</HelperTextItem>
                </HelperText>
              </StackItem>
              {overrideRetry && (
                <RetryPolicyFields register={register} retryDefaults={retryDefaults} isDisabled={isVersionView} />
              )}
            </Stack>
          </FormSection>
        </StackItem>
      )}
    </Stack>
  )
}

export function NodeSettingsForm(props: NodeSettingsFormProps) {
  const {
    timeoutFormat = 'seconds',
    supportsTimeout = true,
    supportsContinueOnFailure = true,
    supportsRetryPolicy = true,
    timeoutNodeType,
    timeoutDefaultSeconds,
  } = props

  const isVersionView = useIsVersionView()
  const { control, register, setValue } = useFormContext<FormWithSettings>()
  const retryPolicy = useWatch({ control, name: 'settings.retry_policy' })
  const continueOnFailure = useWatch({ control, name: 'settings.continue_on_failure' })
  const overrideRetry = retryPolicy !== undefined

  const { defaults } = useWorkflowEngineDefaults()

  const timeoutDefault = resolveTimeoutDefaultSeconds(timeoutDefaultSeconds, timeoutNodeType, defaults)
  const cofDefault = defaults?.continueOnFailure ?? null
  const retryDefaults = defaults?.retry ?? null

  const cofDefaultLabel = getCofDefaultLabel(cofDefault)
  const timeoutPlaceholder = timeoutDefault !== null ? `${String(timeoutDefault)} — system default` : 'System default'

  return (
    <NodeSettingsFormSections
      {...props}
      timeoutFormat={timeoutFormat}
      supportsTimeout={supportsTimeout}
      supportsContinueOnFailure={supportsContinueOnFailure}
      supportsRetryPolicy={supportsRetryPolicy}
      isVersionView={isVersionView}
      control={control}
      register={register}
      setValue={setValue}
      continueOnFailure={continueOnFailure}
      overrideRetry={overrideRetry}
      cofDefaultLabel={cofDefaultLabel}
      timeoutDefault={timeoutDefault}
      timeoutPlaceholder={timeoutPlaceholder}
      retryDefaults={retryDefaults}
    />
  )
}
