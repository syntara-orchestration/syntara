import { createContext } from 'react'

export type FormFieldBuilderOptionsMode = 'default' | 'static-only'

export const FormFieldBuilderOptionsModeContext = createContext<FormFieldBuilderOptionsMode>('default')
