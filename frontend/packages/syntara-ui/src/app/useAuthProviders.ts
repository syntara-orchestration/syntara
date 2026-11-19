import { useEffect, useState } from 'react'

import { orchestratorUiClientHeaders } from '../utils/orchestratorClientHeader'

export type AuthProvider = {
  id: string
  name: string
  provider_type: string
  provider_template?: string | null
}

function isAuthProvider(value: unknown): value is AuthProvider {
  return (
    value != null &&
    typeof value === 'object' &&
    typeof (value as Record<string, unknown>).id === 'string' &&
    typeof (value as Record<string, unknown>).name === 'string'
  )
}

type UseAuthProvidersResult = {
  providers: AuthProvider[]
  isLoading: boolean
}

/**
 * Fetches enabled identity providers from the public /auth/providers endpoint.
 * Uses plain fetch (no auth required). Fails silently — returns empty array on error.
 */
export function useAuthProviders(): UseAuthProvidersResult {
  const [providers, setProviders] = useState<AuthProvider[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let active = true
    const controller = new AbortController()

    const loadProviders = async () => {
      try {
        // eslint-disable-next-line @ansible/no-unapproved-http-client -- pre-auth: fetching providers before token middleware is available
        const response = await fetch('/api/v1/auth/providers', {
          headers: orchestratorUiClientHeaders(),
          signal: controller.signal,
        })
        if (response.ok) {
          const data: unknown = await response.json()
          if (
            active &&
            data != null &&
            typeof data === 'object' &&
            'resources' in data &&
            Array.isArray((data as Record<string, unknown>).resources)
          ) {
            const raw = (data as { resources: unknown[] }).resources
            setProviders(raw.filter(isAuthProvider))
          }
        }
      } catch {
        // Fail silently — local-only login (includes AbortError on unmount)
      } finally {
        if (active) {
          setIsLoading(false)
        }
      }
    }

    // eslint-disable-next-line @typescript-eslint/no-floating-promises -- intentional fire-and-forget from sync useEffect; loadProviders owns errors
    loadProviders()

    return () => {
      active = false
      controller.abort()
    }
  }, [])

  return { providers, isLoading }
}
