import { useParams } from '@tanstack/react-router'

import { SettingsCategoryTab } from './SettingsCategoryTab'
import { useSettingsCategoryTabContext } from './SettingsCategoryTabContext'

export function SettingsCategoryRoute() {
  const { category }: { category?: string } = useParams({ strict: false })
  const context = useSettingsCategoryTabContext()

  if (!context || !category) return null

  return (
    <SettingsCategoryTab
      settings={context.settingsByCategory.get(category) ?? []}
      edits={context.edits}
      onChange={context.onChange}
      onResetField={context.onResetField}
      onValidationChange={context.onValidationChange}
      readOnly={context.readOnly}
    />
  )
}
