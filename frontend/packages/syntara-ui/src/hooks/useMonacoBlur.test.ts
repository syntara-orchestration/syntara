import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { type MonacoEditor, useMonacoBlur } from './useMonacoBlur'

type MockEditor = {
  focus: ReturnType<typeof vi.fn>
  onDidBlurEditorText: ReturnType<typeof vi.fn> & { mock: { calls: unknown[][] } }
}

describe('useMonacoBlur', () => {
  const mockDispose = vi.fn()

  function createMockEditor(): MockEditor {
    return {
      focus: vi.fn(),
      onDidBlurEditorText: vi.fn(() => ({ dispose: mockDispose })),
    }
  }

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('returns getValue that reflects initial code', () => {
    const { result } = renderHook(() => useMonacoBlur('initial'))
    expect(result.current.getValue()).toBe('initial')
  })

  it('getValue updates after setValue', () => {
    const { result } = renderHook(() => useMonacoBlur(''))
    act(() => {
      result.current.setValue('updated')
    })
    expect(result.current.getValue()).toBe('updated')
  })

  it('getValue reflects code when it changes', () => {
    const { result, rerender } = renderHook(({ code }) => useMonacoBlur(code), {
      initialProps: { code: 'first' },
    })
    expect(result.current.getValue()).toBe('first')
    rerender({ code: 'second' })
    expect(result.current.getValue()).toBe('second')
  })

  it('focus calls editor.focus when editor was mounted', () => {
    const { result } = renderHook(() => useMonacoBlur(''))
    const editor = createMockEditor()
    act(() => {
      result.current.handleEditorDidMount(editor as unknown as MonacoEditor)
    })
    act(() => {
      result.current.focus()
    })
    expect(editor.focus).toHaveBeenCalled()
  })

  it('focus does not throw when no editor mounted', () => {
    const { result } = renderHook(() => useMonacoBlur(''))
    expect(() => act(() => result.current.focus())).not.toThrow()
  })

  it('handleEditorDidMount registers blur listener when onBlur provided', () => {
    const onBlur = vi.fn()
    const { result } = renderHook(() => useMonacoBlur('hello', onBlur))
    const editor = createMockEditor()
    act(() => {
      result.current.handleEditorDidMount(editor as unknown as MonacoEditor)
    })
    expect(editor.onDidBlurEditorText).toHaveBeenCalled()
    const calls = editor.onDidBlurEditorText.mock.calls as unknown[][]
    const blurCallback = calls[0]?.[0] as (() => void) | undefined
    expect(blurCallback).toBeDefined()
    act(() => {
      result.current.setValue('blur-value')
    })
    blurCallback?.()
    expect(onBlur).toHaveBeenCalledWith('blur-value')
  })

  it('handleEditorDidMount does not register blur when onBlur is undefined', () => {
    const { result } = renderHook(() => useMonacoBlur(''))
    const editor = createMockEditor()
    act(() => {
      result.current.handleEditorDidMount(editor as unknown as MonacoEditor)
    })
    expect(editor.onDidBlurEditorText).not.toHaveBeenCalled()
  })

  it('disposes blur listener on unmount', () => {
    const onBlur = vi.fn()
    const { result, unmount } = renderHook(() => useMonacoBlur('', onBlur))
    const editor = createMockEditor()
    act(() => {
      result.current.handleEditorDidMount(editor as unknown as MonacoEditor)
    })
    unmount()
    expect(mockDispose).toHaveBeenCalled()
  })

  it('useEffect sets up blur listener when onBlur is added after editor mount', () => {
    const onBlur = vi.fn()
    type Props = { onBlur?: (value: string) => void }
    const initialProps: Props = { onBlur: undefined }
    const { result, rerender } = renderHook(({ onBlur: ob }: Props) => useMonacoBlur('code', ob), {
      initialProps,
    })
    const editor = createMockEditor()
    act(() => {
      result.current.handleEditorDidMount(editor as unknown as MonacoEditor)
    })
    rerender({ onBlur })
    const calls = editor.onDidBlurEditorText.mock.calls as unknown[][]
    const blurCallback = calls[0]?.[0] as (() => void) | undefined
    expect(blurCallback).toBeTypeOf('function')
    act(() => result.current.setValue('from-effect'))
    blurCallback?.()
    expect(onBlur).toHaveBeenCalledWith('from-effect')
  })
})
