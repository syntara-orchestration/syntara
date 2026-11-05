import { createContext } from 'react'

/**
 * The layout-owned DOM slot for form controls rendered in a step editor header.
 * Forms can portal controls into this target so header content stays in the
 * form's React tree without synchronizing rendered nodes back through effects.
 */
export const StepFormHeaderPortalContext = createContext<HTMLElement | null>(null)
