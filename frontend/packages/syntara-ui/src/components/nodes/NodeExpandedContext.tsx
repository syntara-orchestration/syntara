import { createContext, type Dispatch, type SetStateAction } from 'react'

export type NodeExpandedContextValue = [boolean, Dispatch<SetStateAction<boolean>>]

export const NodeExpandedContext = createContext<NodeExpandedContextValue | null>(null)
