import type { ReactNode } from 'react'
import { FormProvider, type FieldValues, type UseFormReturn } from 'react-hook-form'

export type SynFormProps<T extends FieldValues> = {
  /** Form instance from `useSynForm` or `useForm`. */
  form: UseFormReturn<T>
  children: ReactNode
}

/**
 * Provides react-hook-form context so Syn* fields can omit `control`.
 *
 * @example
 * ```tsx
 * const form = useSynForm({ schema, defaultValues, onClose })
 *
 * return (
 *   <Form onSubmit={form.handleSubmit(onSubmit)}>
 *     <SynForm form={form}>
 *       <SynTextField name="name" label="Name" isRequired />
 *     </SynForm>
 *   </Form>
 * )
 * ```
 */
export function SynForm<T extends FieldValues>({ form, children }: Readonly<SynFormProps<T>>) {
  return <FormProvider {...form}>{children}</FormProvider>
}
