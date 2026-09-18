/**
 * Individual field components for AAP prompt-on-launch fields.
 * Extracted from AAPPromptOnLaunchFields.tsx to keep file size under 500 lines.
 */
import {
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  StackItem,
  Switch,
  TextInput,
} from '@patternfly/react-core'
import React, { type ReactElement, useState } from 'react'
import { useFormContext } from 'react-hook-form'

import { FormFieldError } from '../../../components/FormFieldError'
import { SynFormField } from '../../../components/forms/SynFormField'
import { SynTextField } from '../../../components/forms/SynTextField'
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
  return (
    <StackItem>
      <SynFormField<AAPJobTemplateFormData, 'job_type'>
        name="job_type"
        label="Run type"
        labelHelp={nodeHelp.aapJobType}
        fieldId="aap-jobType"
        hideFooter
      >
        {({ field }) => <RunTypeSelect value={field.value ?? ''} onChange={field.onChange} />}
      </SynFormField>
    </StackItem>
  )
}

// ── Verbosity Field ─────────────────────────────────────────────────────

export function VerbosityField() {
  return (
    <StackItem>
      <SynFormField<AAPJobTemplateFormData, 'verbosity'>
        name="verbosity"
        label="Verbosity"
        labelHelp={nodeHelp.aapVerbosity}
        fieldId="aap-verbosity"
        hideFooter
      >
        {({ field }) => <VerbositySelect value={field.value ?? ''} onChange={field.onChange} />}
      </SynFormField>
    </StackItem>
  )
}

// ── Diff Mode Field ─────────────────────────────────────────────────────

export function DiffModeField() {
  return (
    <StackItem>
      <SynFormField<AAPJobTemplateFormData, 'diff_mode'>
        name="diff_mode"
        label="Show changes"
        labelHelp={nodeHelp.aapDiffMode}
        fieldId="aap-diffMode"
        hideFooter
      >
        {({ field }) => (
          <Switch
            id="aap-diffMode"
            aria-label="Show changes"
            isChecked={field.value ?? false}
            onChange={(_event, checked) => field.onChange(checked)}
          />
        )}
      </SynFormField>
    </StackItem>
  )
}

// ── Extra Variables Field ───────────────────────────────────────────────

export type ExtraVariablesFieldProps = {
  readonly editorRef: React.RefObject<ExpandableCodeEditorHandle | null>
}

export function ExtraVariablesField({ editorRef }: ExtraVariablesFieldProps) {
  const { formState } = useFormContext<AAPJobTemplateFormData>()
  const extraVarsMessage = formState.errors.extra_vars?.message

  return (
    <StackItem>
      <SynFormField<AAPJobTemplateFormData, 'extra_vars'>
        name="extra_vars"
        label="Extra variables"
        labelHelp={nodeHelp.aapExtraVars}
        fieldId="aap-extra_vars"
        hideFooter
      >
        {({ field }) => (
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
      </SynFormField>
      {extraVarsMessage && <FormFieldError message={extraVarsMessage} />}
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
  return (
    <StackItem>
      <SynTextField<AAPJobTemplateFormData, typeof name>
        name={name}
        label={label}
        fieldId={fieldId}
        labelHelp={labelHelp}
      />
    </StackItem>
  )
}

// ── Number Input Field ──────────────────────────────────────────────────

type AAPNumberFieldName = 'forks' | 'job_slice_count'

export type NumberInputFieldProps = {
  readonly label: string
  readonly fieldId: string
  readonly name: AAPNumberFieldName
  readonly placeholder: string
  readonly min: number
  readonly labelHelp?: ReactElement
}

export function NumberInputField({ label, fieldId, name, placeholder, min, labelHelp }: NumberInputFieldProps) {
  return (
    <StackItem>
      <SynFormField<AAPJobTemplateFormData, AAPNumberFieldName>
        name={name}
        label={label}
        fieldId={fieldId}
        labelHelp={labelHelp}
      >
        {({ field, fieldState }) => (
          <TextInput
            id={fieldId}
            type="number"
            placeholder={placeholder}
            min={min}
            validated={fieldState.error ? 'error' : 'default'}
            value={typeof field.value === 'number' ? String(field.value) : ''}
            onChange={(_event, value) => field.onChange(value === '' ? undefined : Number(value))}
            onBlur={field.onBlur}
            name={field.name}
          />
        )}
      </SynFormField>
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
  return (
    <StackItem>
      <SynFormField<AAPJobTemplateFormData, typeof name>
        name={name}
        label={label}
        labelHelp={labelHelp}
        fieldId={fieldId}
        hideFooter
      >
        {({ field }) => {
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
      </SynFormField>
    </StackItem>
  )
}
