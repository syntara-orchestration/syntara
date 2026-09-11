/**
 * Individual field components for AAP prompt-on-launch fields.
 * Extracted from AAPPromptOnLaunchFields.tsx to keep file size under 500 lines.
 */
import {
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  StackItem,
  Switch,
  TextInput,
} from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import React, { type ReactElement, useState } from 'react'
import { Controller, useFormContext } from 'react-hook-form'

import { TagInput } from '../../../components/forms/TagInput'
import { SynSelect } from '../../../components/SynSelect'
import { ExpandableCodeEditor, type ExpandableCodeEditorHandle } from '../components/ExpandableCodeEditor'

import type { AAPJobTemplateFormData } from './aapJobTemplateSchema'
import { nodeHelp } from './shared/nodeFieldHelp'

// ── Select sub-components ────────────────────────────────────────────────

const RUN_TYPE_OPTIONS = [
  { value: 'run', label: 'Run' },
  { value: 'check', label: 'Check (Dry Run)' },
]

function RunTypeSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = RUN_TYPE_OPTIONS.find((o) => o.value === value)?.label
  return (
    <SynSelect
      id="aap-jobType"
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
          isPlaceholder={!value}
          aria-label="Run type"
        >
          {selectedLabel ?? '[ run type ]'}
        </MenuToggle>
      )}
    >
      <SelectList>
        {RUN_TYPE_OPTIONS.map((o) => (
          <SelectOption key={o.value} value={o.value}>
            {o.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

const VERBOSITY_OPTIONS = [
  { value: '0', label: '0 - Normal' },
  { value: '1', label: '1 - Verbose' },
  { value: '2', label: '2 - More Verbose' },
  { value: '3', label: '3 - Debug' },
  { value: '4', label: '4 - Connection Debug' },
  { value: '5', label: '5 - WinRM Debug' },
]

function VerbositySelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = VERBOSITY_OPTIONS.find((o) => o.value === value)?.label
  return (
    <SynSelect
      id="aap-verbosity"
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
          isPlaceholder={!value}
          aria-label="Verbosity"
        >
          {selectedLabel ?? '[ verbosity ]'}
        </MenuToggle>
      )}
    >
      <SelectList>
        {VERBOSITY_OPTIONS.map((o) => (
          <SelectOption key={o.value} value={o.value}>
            {o.label}
          </SelectOption>
        ))}
      </SelectList>
    </SynSelect>
  )
}

// ── Run Type Field ──────────────────────────────────────────────────────

export function RunTypeField() {
  const { control } = useFormContext<AAPJobTemplateFormData>()

  return (
    <StackItem>
      <FormGroup label="Run type" labelHelp={nodeHelp.aapJobType} fieldId="aap-jobType">
        <Controller
          control={control}
          name="job_type"
          render={({ field }) => <RunTypeSelect value={field.value ?? ''} onChange={field.onChange} />}
        />
      </FormGroup>
    </StackItem>
  )
}

// ── Verbosity Field ─────────────────────────────────────────────────────

export function VerbosityField() {
  const { control } = useFormContext<AAPJobTemplateFormData>()

  return (
    <StackItem>
      <FormGroup label="Verbosity" labelHelp={nodeHelp.aapVerbosity} fieldId="aap-verbosity">
        <Controller
          control={control}
          name="verbosity"
          render={({ field }) => <VerbositySelect value={field.value ?? ''} onChange={field.onChange} />}
        />
      </FormGroup>
    </StackItem>
  )
}

// ── Diff Mode Field ─────────────────────────────────────────────────────

export function DiffModeField() {
  const { control } = useFormContext<AAPJobTemplateFormData>()

  return (
    <StackItem>
      <FormGroup label="Show changes" labelHelp={nodeHelp.aapDiffMode} fieldId="aap-diffMode">
        <Controller
          control={control}
          name="diff_mode"
          render={({ field }) => (
            <Switch
              id="aap-diffMode"
              aria-label="Show changes"
              isChecked={field.value ?? false}
              onChange={(_event, checked) => field.onChange(checked)}
            />
          )}
        />
      </FormGroup>
    </StackItem>
  )
}

// ── Extra Variables Field ───────────────────────────────────────────────

export type ExtraVariablesFieldProps = {
  readonly editorRef: React.RefObject<ExpandableCodeEditorHandle | null>
}

export function ExtraVariablesField({ editorRef }: ExtraVariablesFieldProps) {
  const {
    control,
    formState: { errors },
  } = useFormContext<AAPJobTemplateFormData>()
  const extraVarsMessage = errors.extra_vars?.message

  return (
    <StackItem>
      <FormGroup label="Extra variables" labelHelp={nodeHelp.aapExtraVars} fieldId="aap-extra_vars">
        <Controller
          control={control}
          name="extra_vars"
          render={({ field }) => (
            <div className={extraVarsMessage ? 'pf-v6-c-form-control pf-m-error' : undefined}>
              <ExpandableCodeEditor
                ref={editorRef}
                code={field.value ?? ''}
                onCodeChange={field.onChange}
                onBlur={field.onBlur}
                language="json"
                height="150px"
                modalTitle="Edit extra variables"
                ariaLabel="Extra Variables"
              />
            </div>
          )}
        />
        {extraVarsMessage && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                {extraVarsMessage}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </FormGroup>
    </StackItem>
  )
}

// ── Text Input Field ────────────────────────────────────────────────────

export type TextInputFieldProps = {
  readonly label: string
  readonly fieldId: string
  readonly name: keyof AAPJobTemplateFormData
  readonly labelHelp?: ReactElement
}

export function TextInputField({ label, fieldId, name, labelHelp }: TextInputFieldProps) {
  const { register } = useFormContext<AAPJobTemplateFormData>()

  return (
    <StackItem>
      <FormGroup label={label} labelHelp={labelHelp} fieldId={fieldId}>
        <TextInput {...register(name)} id={fieldId} type="text" />
      </FormGroup>
    </StackItem>
  )
}

// ── Number Input Field ──────────────────────────────────────────────────

export type NumberInputFieldProps = {
  readonly label: string
  readonly fieldId: string
  readonly name: keyof AAPJobTemplateFormData
  readonly placeholder: string
  readonly min: number
  readonly labelHelp?: ReactElement
}

export function NumberInputField({ label, fieldId, name, placeholder, min, labelHelp }: NumberInputFieldProps) {
  const { register } = useFormContext<AAPJobTemplateFormData>()

  return (
    <StackItem>
      <FormGroup label={label} labelHelp={labelHelp} fieldId={fieldId}>
        <TextInput
          {...register(name, { valueAsNumber: true })}
          id={fieldId}
          type="number"
          placeholder={placeholder}
          min={min}
        />
      </FormGroup>
    </StackItem>
  )
}

// ── Tag Input Field ─────────────────────────────────────────────────────

export type TagInputFieldProps = {
  readonly label: string
  readonly fieldId: string
  readonly name: keyof AAPJobTemplateFormData
  readonly placeholder: string
  readonly helperText: string
  readonly labelHelp?: ReactElement
}

export function TagInputField({ label, fieldId, name, placeholder, helperText, labelHelp }: TagInputFieldProps) {
  const { control } = useFormContext<AAPJobTemplateFormData>()

  return (
    <StackItem>
      <FormGroup label={label} labelHelp={labelHelp} fieldId={fieldId}>
        <Controller
          control={control}
          name={name}
          render={({ field }) => {
            const items =
              typeof field.value === 'string' && field.value
                ? field.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                : []
            return (
              <TagInput
                id={fieldId}
                value={items}
                onChange={(arr) => field.onChange(arr.join(', '))}
                ariaLabel={label}
                placeholder={placeholder}
                helperText={helperText}
              />
            )
          }}
        />
      </FormGroup>
    </StackItem>
  )
}
