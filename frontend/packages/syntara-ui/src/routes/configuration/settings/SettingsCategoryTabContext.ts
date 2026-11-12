import type { SettingsAPI } from '@syntara/contracts'
import { createContext, use } from 'react'

type RuntimeSetting = SettingsAPI.components['schemas']['RuntimeSettingRead']

type SettingsCategoryTabContextValue = {
  settingsByCategory: Map<string, RuntimeSetting[]>
  edits: Map<string, unknown>
  onChange: (key: string, value: unknown) => void
  onResetField: (key: string) => void
  onValidationChange: (key: string, hasError: boolean) => void
  readOnly: boolean
}

export const SettingsCategoryTabContext = createContext<SettingsCategoryTabContextValue | null>(null)

export function useSettingsCategoryTabContext() {
  return use(SettingsCategoryTabContext)
}
