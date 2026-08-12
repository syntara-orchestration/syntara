import { useCallback, useEffect, useRef, useState } from 'react'

import { OIDC_AUTHORIZE_PATH } from '../../../../client'
import { generateUUID } from '../../../../utils/generateUUID'

export const NONCE_STORAGE_KEY = 'syntara-test-signin-nonce'
export const RESULT_STORAGE_KEY = 'syntara-test-signin'

type UseTestSignInOptions = {
  providerId?: string
  onResult: (claims: Record<string, unknown>) => void
  onError?: () => void
}

type UseTestSignInReturn = {
  openTestSignIn: () => void
  isListening: boolean
}

export function useTestSignIn({ providerId, onResult, onError }: UseTestSignInOptions): UseTestSignInReturn {
  const [isListening, setIsListening] = useState(false)
  const nonceRef = useRef<string | null>(null)
  const popupRef = useRef<Window | null>(null)
  const onResultRef = useRef(onResult)
  // eslint-disable-next-line react-hooks/refs -- keep refs in sync so the poll effect doesn't need these as dependencies
  onResultRef.current = onResult
  const onErrorRef = useRef(onError)
  // eslint-disable-next-line react-hooks/refs
  onErrorRef.current = onError

  useEffect(() => {
    if (!isListening) return

    function consumeResult(): boolean {
      const raw = localStorage.getItem(RESULT_STORAGE_KEY)
      if (!raw) return false

      let parsed: Record<string, unknown>
      try {
        const obj: unknown = JSON.parse(raw)
        if (!obj || typeof obj !== 'object') return false
        parsed = obj as Record<string, unknown>
      } catch {
        return false
      }

      if (
        parsed.type !== 'test-signin' ||
        parsed.nonce !== nonceRef.current ||
        typeof parsed.claims !== 'object' ||
        !parsed.claims
      )
        return false

      localStorage.removeItem(RESULT_STORAGE_KEY)
      localStorage.removeItem(NONCE_STORAGE_KEY)
      nonceRef.current = null
      onResultRef.current(parsed.claims as Record<string, unknown>)
      return true
    }

    // Poll localStorage for the result until it arrives or the timeout
    // expires. We avoid relying on popupRef.closed because browsers
    // report inconsistent values when the popup opens as a tab.
    const startedAt = Date.now()
    const TIMEOUT_MS = 120_000
    const pollTimer = setInterval(() => {
      if (consumeResult()) {
        clearInterval(pollTimer)
        setIsListening(false)
        return
      }
      if (Date.now() - startedAt > TIMEOUT_MS) {
        clearInterval(pollTimer)
        setIsListening(false)
        onErrorRef.current?.()
      }
    }, 200)

    return () => {
      clearInterval(pollTimer)
    }
  }, [isListening])

  const openTestSignIn = useCallback(() => {
    if (!providerId) return

    const nonce = generateUUID()
    nonceRef.current = nonce
    // Store the nonce in localStorage so the popup can read it after the OAuth
    // redirect chain (window.opener is nullified by cross-origin navigations).
    // The nonce is verified in-memory via nonceRef to prevent injection.
    localStorage.setItem(NONCE_STORAGE_KEY, nonce)
    localStorage.removeItem(RESULT_STORAGE_KEY)

    const popup = globalThis.open(
      `${OIDC_AUTHORIZE_PATH}?provider_id=${encodeURIComponent(providerId)}&flow=test_signin`,
      'test-signin',
      'width=600,height=700'
    )
    popupRef.current = popup
    if (!popup) {
      onErrorRef.current?.()
      return
    }
    setIsListening(true)
  }, [providerId])

  return { openTestSignIn, isListening }
}
