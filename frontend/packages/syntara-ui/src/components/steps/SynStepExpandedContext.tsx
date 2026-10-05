import { createContext, type Dispatch, type SetStateAction } from 'react'

export type SynStepExpandedContextValue = [boolean, Dispatch<SetStateAction<boolean>>]

export const SynStepExpandedContext = createContext<SynStepExpandedContextValue | null>(null)
