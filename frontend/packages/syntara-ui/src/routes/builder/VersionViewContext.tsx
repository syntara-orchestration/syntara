import { createContext, use } from 'react'

export const VersionViewContext = createContext(false)
export const StepFormReadOnlyContext = createContext(false)

export function useIsVersionView(): boolean {
  return use(VersionViewContext)
}

export function useIsStepFormReadOnly(): boolean {
  return useIsVersionView() || use(StepFormReadOnlyContext)
}
