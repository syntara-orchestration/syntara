import { createContext } from 'react'

export const NodeExpandedAllContext = createContext<{
  expandAllEvent: EventTarget
  collapseAllEvent: EventTarget
}>({
  expandAllEvent: new EventTarget(),
  collapseAllEvent: new EventTarget(),
})
