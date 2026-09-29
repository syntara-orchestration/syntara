import { createContext, use } from 'react'

export const FormFieldBuilderCommitContext = createContext<(() => void) | null>(null)

export function useFormFieldBuilderCommit(): () => void {
  const commit = use(FormFieldBuilderCommitContext)
  if (!commit) {
    throw new Error('useFormFieldBuilderCommit must be used within SynFormFieldBuilder')
  }
  return commit
}
