import { createContext, use } from 'react'

export const VersionViewContext = createContext(false)

export function useIsVersionView(): boolean {
  return use(VersionViewContext)
}
