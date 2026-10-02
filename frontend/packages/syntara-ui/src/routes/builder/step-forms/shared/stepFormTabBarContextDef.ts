import { createContext } from 'react'
import type { ReactNode } from 'react'

export type StepFormTabBarContextValue = {
  tabBarAction?: ReactNode
}

export const StepFormTabBarContext = createContext<StepFormTabBarContextValue | null>(null)
