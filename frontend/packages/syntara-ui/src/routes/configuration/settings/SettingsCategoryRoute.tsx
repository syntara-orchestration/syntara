import { useRouterState } from '@tanstack/react-router'

import { AppRoute } from '../../../app/AppRoute'
import { SynPageTitle } from '../../../components/SynPageTitle'

import { SettingsCategoryTab } from './SettingsCategoryTab'
import { useSettingsCategoryTabContext } from './SettingsCategoryTabContext'

const basePath = `${AppRoute.SystemAdministration.Settings}/`

export function SettingsCategoryRoute() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const category = pathname.startsWith(basePath) ? pathname.slice(basePath.length).split('/')[0] : undefined
  const context = useSettingsCategoryTabContext()

  if (!context || !category) return null

  return (
    <>
      <SynPageTitle segments={['Settings']} />
      <SettingsCategoryTab
        settings={context.settingsByCategory.get(category) ?? []}
        edits={context.edits}
        onChange={context.onChange}
        onResetField={context.onResetField}
        onValidationChange={context.onValidationChange}
        readOnly={context.readOnly}
      />
    </>
  )
}
