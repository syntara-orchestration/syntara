import { useMemo } from 'react'
import type { ReactNode } from 'react'

import { StepFormTabBarContext } from './stepFormTabBarContextDef'

export function StepFormTabBarProvider({ children, tabBarAction }: { children: ReactNode; tabBarAction?: ReactNode }) {
  const value = useMemo(() => ({ tabBarAction }), [tabBarAction])
  return <StepFormTabBarContext.Provider value={value}>{children}</StepFormTabBarContext.Provider>
}
