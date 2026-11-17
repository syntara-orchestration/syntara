import { createContext, use } from 'react'

/** When true, hide client-side zod errors until verify/save findings are applied (workflow step editor). */
export const FormFieldBuilderDraftModeContext = createContext(false)

export function useFormFieldBuilderDraftMode(): boolean {
  return use(FormFieldBuilderDraftModeContext)
}
