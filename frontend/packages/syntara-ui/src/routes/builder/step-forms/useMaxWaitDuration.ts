import { useQuery } from '@tanstack/react-query'

import { settingsFetchClient } from '../../../client'

const SETTING_KEY = 'workflow_engine.max_wait_duration_seconds'
export const DEFAULT_MAX_WAIT_SECONDS = 2_592_000 // 30 days

export function useMaxWaitDuration() {
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['setting', SETTING_KEY],
    queryFn: async () => {
      const res = await settingsFetchClient.GET('/settings/{key}', {
        params: { path: { key: SETTING_KEY } },
      })
      return res.data ?? null
    },
    staleTime: 0,
    gcTime: 0,
  })

  const raw = data?.effective_value
  const maxSeconds = typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_MAX_WAIT_SECONDS

  return { maxSeconds, isLoading: isLoading || isFetching }
}

/** Fetch the current max wait duration directly (no cache). Use in async handlers like Run. */
export async function fetchMaxWaitDuration(): Promise<number> {
  try {
    const res = await settingsFetchClient.GET('/settings/{key}', {
      params: { path: { key: SETTING_KEY } },
    })
    const value = res.data?.effective_value
    return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : DEFAULT_MAX_WAIT_SECONDS
  } catch {
    return DEFAULT_MAX_WAIT_SECONDS
  }
}
