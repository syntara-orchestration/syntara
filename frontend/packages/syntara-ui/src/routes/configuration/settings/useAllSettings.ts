import type { SettingsAPI } from '@syntara/contracts'
import { useQuery } from '@tanstack/react-query'

import { settingsFetchClient } from '../../../client'
import { fetchAllPages, MAX_PAGE_SIZE } from '../../../utils/fetchAllPages'

type RuntimeSettingRead = SettingsAPI.components['schemas']['RuntimeSettingRead']

async function fetchAllSettingsPages(): Promise<RuntimeSettingRead[]> {
  return fetchAllPages<RuntimeSettingRead>((cursor) =>
    settingsFetchClient.GET('/settings', {
      params: { query: { limit: MAX_PAGE_SIZE, cursor } },
    })
  )
}

/** Full settings list for the Settings page (cursor pagination under the hood). */
export function useAllSettings(options?: { enabled?: boolean }) {
  const enabled = options?.enabled ?? true
  const {
    data: settings = [],
    isPending,
    error,
    refetch,
  } = useQuery({
    queryKey: ['all-settings'],
    queryFn: fetchAllSettingsPages,
    enabled,
  })
  return { settings, isLoading: enabled && isPending, error, refetch }
}
