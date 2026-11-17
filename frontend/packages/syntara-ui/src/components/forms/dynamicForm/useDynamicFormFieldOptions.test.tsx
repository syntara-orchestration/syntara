import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { FormFieldTypeEnum, parseFormDefinition } from '../../../forms'

import { useDynamicFormFieldOptions } from './useDynamicFormFieldOptions'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

describe('useDynamicFormFieldOptions', () => {
  it('returns static options without a query', () => {
    const field = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'priority',
          label: 'Priority',
          options: {
            source: 'static',
            values: [{ display_label: 'Low', value: 'low' }],
          },
        },
      ],
    }).fields[0]

    const { result } = renderHook(() => useDynamicFormFieldOptions(field), { wrapper: createWrapper() })

    expect(result.current.options).toEqual([{ label: 'Low', value: 'low' }])
    expect(result.current.isLoading).toBe(false)
    expect(result.current.loadErrorMessage).toBeNull()
  })

  it('returns resolved options synchronously without invoking the resolver', () => {
    const field = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.MULTI_SELECT,
          value_name: 'regions',
          label: 'Regions',
          options: {
            source: 'dynamic_resolved',
            values: [
              { display_label: 'US East', value: 1 },
              { display_label: 'EU West', value: 'eu-west-1' },
            ],
          },
        },
      ],
    }).fields[0]
    const resolveDynamicOptions = vi.fn()

    const { result } = renderHook(() => useDynamicFormFieldOptions(field, resolveDynamicOptions), {
      wrapper: createWrapper(),
    })

    expect(result.current.options).toEqual([
      { label: 'US East', value: 1 },
      { label: 'EU West', value: 'eu-west-1' },
    ])
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isError).toBe(false)
    expect(resolveDynamicOptions).not.toHaveBeenCalled()
  })

  it('fetches and normalizes dynamic records via resolver', async () => {
    const field = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'region',
          label: 'Region',
          options: {
            source: 'dynamic',
            expression: '${nodes.upstream.regions}',
            label_key: 'name',
            value_key: 'id',
          },
        },
      ],
    }).fields[0]

    const resolveDynamicOptions = vi.fn().mockResolvedValue([{ name: 'US East', id: 'use1' }])

    const { result } = renderHook(() => useDynamicFormFieldOptions(field, resolveDynamicOptions), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.options).toEqual([{ label: 'US East', value: 'use1' }])
    })
    expect(resolveDynamicOptions).toHaveBeenCalledWith(
      '${nodes.upstream.regions}',
      expect.objectContaining({ value_name: 'region' })
    )
  })

  it('reports error when dynamic field has no resolver', () => {
    const field = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'region',
          label: 'Region',
          options: { source: 'dynamic', expression: '${nodes.x}', label_key: 'label', value_key: 'value' },
        },
      ],
    }).fields[0]

    const { result } = renderHook(() => useDynamicFormFieldOptions(field), { wrapper: createWrapper() })

    expect(result.current.isError).toBe(true)
    expect(result.current.loadErrorMessage).toBe('Dynamic options require a resolver.')
  })

  it('surfaces query failures', async () => {
    const field = parseFormDefinition({
      fields: [
        {
          type: FormFieldTypeEnum.DROPDOWN,
          value_name: 'region',
          label: 'Region',
          options: { source: 'dynamic', expression: '${nodes.x}', label_key: 'label', value_key: 'value' },
        },
      ],
    }).fields[0]

    const resolveDynamicOptions = vi.fn().mockRejectedValue(new Error('Network down'))

    const { result } = renderHook(() => useDynamicFormFieldOptions(field, resolveDynamicOptions), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.loadErrorMessage).toBe('Network down')
    })
  })
})
