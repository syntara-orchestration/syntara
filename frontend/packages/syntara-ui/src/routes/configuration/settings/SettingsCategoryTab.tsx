import { ActionGroup, Button, Form, FormSection } from '@patternfly/react-core'
import type { SettingsAPI } from '@syntara/contracts'
import { useMemo } from 'react'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import { useDialogState } from '../../../hooks/useDialogState'

import { SettingField } from './SettingField'
import { valuesEqual } from './valuesEqual'

type RuntimeSetting = SettingsAPI.components['schemas']['RuntimeSettingRead']

function orderByDependency(items: RuntimeSetting[]): RuntimeSetting[] {
  const independent = items.filter((s) => !s.depends_on)
  const byTarget = new Map<string, RuntimeSetting[]>()
  for (const s of items) {
    if (!s.depends_on) continue
    if (!byTarget.has(s.depends_on)) byTarget.set(s.depends_on, [])
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: key was just set via byTarget.set(s.depends_on, []) above
    byTarget.get(s.depends_on)!.push(s)
  }
  const parentKeys = new Set(independent.map((s) => s.key))
  const ordered: RuntimeSetting[] = []
  for (const s of independent) {
    ordered.push(s, ...(byTarget.get(s.key) ?? []))
  }
  for (const [key, deps] of byTarget) {
    if (!parentKeys.has(key)) ordered.push(...deps)
  }
  return ordered
}

type SettingsCategoryTabProps = {
  readonly settings: RuntimeSetting[]
  readonly edits: Map<string, unknown>
  readonly onChange: (key: string, value: unknown) => void
  readonly onResetField: (key: string) => void
  readonly onValidationChange?: (key: string, hasError: boolean) => void
  readonly readOnly?: boolean
}

export function SettingsCategoryTab({
  settings,
  edits,
  onChange,
  onResetField,
  onValidationChange,
  readOnly,
}: SettingsCategoryTabProps) {
  const resetDialog = useDialogState()

  const groups = useMemo(() => {
    const grouped = new Map<string, RuntimeSetting[]>()
    for (const setting of settings) {
      const group = setting.group ?? ''
      if (!grouped.has(group)) grouped.set(group, [])
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: key was just set via grouped.set(group, []) above
      grouped.get(group)!.push(setting)
    }
    for (const [key, groupSettings] of grouped) {
      grouped.set(key, orderByDependency(groupSettings))
    }
    return grouped
  }, [settings])

  const settingsByKey = useMemo(() => new Map(settings.map((s) => [s.key, s])), [settings])

  const getDisplayValue = (setting: RuntimeSetting) => {
    if (edits.has(setting.key)) return edits.get(setting.key)
    return setting.effective_value
  }

  const hasNonDefaults = settings.some((s) => {
    const displayValue = edits.has(s.key) ? edits.get(s.key) : s.effective_value
    return !valuesEqual(displayValue, s.default_value)
  })

  const handleResetAll = () => {
    for (const setting of settings) {
      onChange(setting.key, setting.default_value)
    }
    resetDialog.close()
  }

  return (
    <Form>
      {Array.from(groups.entries()).map(([groupName, groupSettings]) => {
        return (
          <FormSection key={groupName} title={groupName || undefined}>
            {groupSettings.map((setting) => {
              if (setting.depends_on) {
                const target = settingsByKey.get(setting.depends_on)
                if (target && !getDisplayValue(target)) return null
              }

              return (
                <SettingField
                  key={setting.key}
                  setting={setting}
                  value={getDisplayValue(setting)}
                  onChange={onChange}
                  onResetSingle={onResetField}
                  onValidationChange={onValidationChange}
                  readOnly={readOnly}
                />
              )
            })}
          </FormSection>
        )
      })}

      {!readOnly && (
        <ActionGroup>
          <Button variant="secondary" onClick={() => resetDialog.open(undefined)} isDisabled={!hasNonDefaults}>
            Reset to defaults
          </Button>
        </ActionGroup>
      )}

      <SynConfirmationDialog
        isOpen={resetDialog.isOpen}
        onClose={resetDialog.close}
        onConfirm={handleResetAll}
        title="Reset settings?"
        titleIconVariant="warning"
        confirmLabel="Reset all"
        confirmVariant="danger"
      >
        This will reset all configuration values on this page to their factory defaults. These changes will not take
        effect until you click Save changes.
      </SynConfirmationDialog>
    </Form>
  )
}
