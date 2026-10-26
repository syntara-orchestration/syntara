import type { ReactNode } from 'react'

import {
  FormFieldBuilderOptionsModeContext,
  type FormFieldBuilderOptionsMode,
} from './formFieldBuilderOptionsModeContext'

export function FormFieldBuilderOptionsModeProvider({
  mode,
  children,
}: Readonly<{ mode: FormFieldBuilderOptionsMode; children: ReactNode }>) {
  return (
    <FormFieldBuilderOptionsModeContext.Provider value={mode}>{children}</FormFieldBuilderOptionsModeContext.Provider>
  )
}
