import { use } from 'react'

import { StepFormTabBarContext } from './stepFormTabBarContextDef'

export function useStepFormTabBar() {
  const context = use(StepFormTabBarContext)
  return context?.tabBarAction
}
