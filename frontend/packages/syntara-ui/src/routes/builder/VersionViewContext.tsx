import { createContext, use } from 'react'

export const VersionViewContext = createContext(false)
export const StepFormReadOnlyContext = createContext<boolean | string>(false)

export function useIsVersionView(): boolean {
  return use(VersionViewContext)
}

export function useIsStepFormReadOnly(): boolean {
  return useIsVersionView() || Boolean(use(StepFormReadOnlyContext))
}

export function useStepFormReadOnlyReason(readOnly?: boolean): string | null {
  const reason = use(StepFormReadOnlyContext)
  if (useIsVersionView()) return 'You are viewing a previous version. Return to the editor to make changes.'
  if (!readOnly) return null
  return typeof reason === 'string' ? reason : 'You do not have permission to edit this workflow.'
}
