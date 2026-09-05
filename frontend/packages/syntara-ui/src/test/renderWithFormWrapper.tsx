import { zodResolver } from '@hookform/resolvers/zod'
import type { ReactNode } from 'react'
import type { DefaultValues, FieldValues, Resolver, UseFormReturn } from 'react-hook-form'
import { useForm } from 'react-hook-form'
import type { ZodType } from 'zod'

type ZodResolverSchema = Parameters<typeof zodResolver>[0]

export type RenderWithFormWrapperProps<T extends FieldValues> = {
  schema: ZodType<T>
  defaultValues: DefaultValues<T>
  children: (form: UseFormReturn<T>) => ReactNode
}

export function RenderWithFormWrapper<T extends FieldValues>({
  schema,
  defaultValues,
  children,
}: RenderWithFormWrapperProps<T>) {
  const form = useForm<T>({
    resolver: zodResolver(schema as ZodResolverSchema, undefined, { mode: 'sync' }) as Resolver<T>,
    defaultValues,
  })

  return <>{children(form)}</>
}
