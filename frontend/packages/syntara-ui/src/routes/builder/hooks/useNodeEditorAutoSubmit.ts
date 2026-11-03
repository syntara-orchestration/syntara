import { createContext, useEffect, useRef, type MutableRefObject } from 'react'
import type { FieldValues, UseFormReturn } from 'react-hook-form'

type AutoSubmitFn = () => Promise<boolean>

export const NodeEditorAutoSubmitContext = createContext<MutableRefObject<AutoSubmitFn | null>>({ current: null })

export function useNodeEditorAutoSubmitRef() {
  return useRef<AutoSubmitFn | null>(null)
}

export function useRegisterAutoSubmit<T extends FieldValues>(
  autoSubmitRef: MutableRefObject<AutoSubmitFn | null>,
  methods: UseFormReturn<T>,
  onSubmit: (data: T) => boolean | void | Promise<boolean | void>,
  beforeSubmit?: () => void
) {
  const onSubmitRef = useRef(onSubmit)
  const beforeSubmitRef = useRef(beforeSubmit)
  useEffect(() => {
    onSubmitRef.current = onSubmit
  }, [onSubmit])
  useEffect(() => {
    beforeSubmitRef.current = beforeSubmit
  }, [beforeSubmit])

  useEffect(() => {
    autoSubmitRef.current = async () => {
      let succeeded = false
      try {
        beforeSubmitRef.current?.()
        await methods.handleSubmit(
          async (data) => {
            const result = await onSubmitRef.current(data)
            succeeded = result !== false
          },
          () => {
            succeeded = false
          }
        )()
      } catch {
        succeeded = false
      }
      return succeeded
    }
    return () => {
      autoSubmitRef.current = null
    }
  }, [autoSubmitRef, methods])
}
