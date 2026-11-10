import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'

import type { TriggerFormData } from './triggerFormSchema'
import { useWebhookUrl } from './useWebhookUrl'

function createWrapper(webhookPath: string) {
  return function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    const methods = useForm<TriggerFormData>({ defaultValues: { webhookPath } })
    return <FormProvider {...methods}>{children}</FormProvider>
  }
}

describe('useWebhookUrl', () => {
  it('returns base URL when webhook path is empty', () => {
    const { result } = renderHook(() => useWebhookUrl('https://example.com/webhooks'), {
      wrapper: createWrapper(''),
    })

    expect(result.current).toBe('https://example.com/webhooks')
  })

  it('appends normalized path to base URL', () => {
    const { result } = renderHook(() => useWebhookUrl('https://example.com/webhooks'), {
      wrapper: createWrapper('my-hook'),
    })

    expect(result.current).toBe('https://example.com/webhooks/my-hook')
  })

  it('strips leading slashes from webhook path', () => {
    const { result } = renderHook(() => useWebhookUrl('https://example.com/webhooks'), {
      wrapper: createWrapper('///my-hook'),
    })

    expect(result.current).toBe('https://example.com/webhooks/my-hook')
  })

  it('returns base URL when path is only slashes', () => {
    const { result } = renderHook(() => useWebhookUrl('https://example.com/webhooks'), {
      wrapper: createWrapper('///'),
    })

    expect(result.current).toBe('https://example.com/webhooks')
  })
})
