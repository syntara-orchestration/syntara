import { createContext } from 'react'

export const SynStepExpandedAllContext = createContext<{
  expandAllEvent: EventTarget
  collapseAllEvent: EventTarget
}>({
  expandAllEvent: new EventTarget(),
  collapseAllEvent: new EventTarget(),
})
