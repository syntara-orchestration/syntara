import { FormGroup, MenuToggle, SelectList, SelectOption, Stack, StackItem } from '@patternfly/react-core'
import { useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'

import { SynTextField } from '../../../components/forms/SynTextField'
import { SynSelect } from '../../../components/SynSelect'
import { useWorkflowEngineDefaults } from '../hooks/useWorkflowEngineDefaults'
import { useIsVersionView } from '../VersionViewContext'

import { nodeHelp } from './shared/nodeFieldHelp'
import type { NodeSettingsFormData } from './shared/nodeSettingsSchema'

type FormWithSettings = { settings: Omit<NodeSettingsFormData, 'retry_policy'> }

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
    description: () => 'Downstream steps continue executing even if this step fails.',
  },
  {
    value: 'off' as const,
    label: 'Stop workflow or branch on failure',
    description: () => 'The workflow (or current branch) stops at this step if it fails.',
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

function getCofDefaultLabel(cofDefault: boolean | null): string {
  if (cofDefault === null) return ''
  if (cofDefault) return ' (system default: continue on failure)'
  return ' (system default: stop on failure)'
}

export function SubWorkflowSettingsForm() {
  const isVersionView = useIsVersionView()
  const { control, setValue } = useFormContext<FormWithSettings>()
  const continueOnFailure = useWatch({ control, name: 'settings.continue_on_failure' })

  const [isCofOpen, setIsCofOpen] = useState(false)

  const { defaults } = useWorkflowEngineDefaults()

  const cofDefault = defaults?.continueOnFailure ?? null

  const cofDefaultLabel = getCofDefaultLabel(cofDefault)
  const timeoutPlaceholder = 'System default'

  const selected = cofValueFromBool(continueOnFailure)
  const selectedLabel = COF_OPTIONS.find((o) => o.value === selected)?.label ?? 'System default'

  function handleCofSelect(_event: React.MouseEvent | undefined, value: string | number | undefined) {
    setValue('settings.continue_on_failure', cofValueToBool(value as CofValue))
    setIsCofOpen(false)
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <FormGroup label="On failure" labelHelp={nodeHelp.onFailureBehavior} fieldId="subworkflow-settings-cof">
          <SynSelect
            id="subworkflow-settings-cof"
            isOpen={isCofOpen}
            selected={selected}
            onSelect={handleCofSelect}
            onOpenChange={setIsCofOpen}
            shouldFocusToggleOnSelect
            toggle={(ref) => (
              <MenuToggle
                ref={ref}
                onClick={() => setIsCofOpen((o) => !o)}
                isExpanded={isCofOpen}
                isFullWidth
                isDisabled={isVersionView}
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

      <StackItem>
        <SynTextField
          name="settings.timeout"
          label="Timeout (seconds)"
          labelHelp={nodeHelp.timeout}
          fieldId="subworkflow-settings-timeout"
          type="number"
          min={1}
          placeholder={timeoutPlaceholder}
          isDisabled={isVersionView}
        />
      </StackItem>
    </Stack>
  )
}
