import { createContext } from 'react'

import type { NavigationTarget } from '../../app/typed-route-destinations'

export type DirtyCheckOptions = {
  check: () => boolean
  exitWithoutSaving?: () => void
  saveAndExit?: () => Promise<boolean>
  title?: string
  body?: string
  saveLabel?: string
}

export type UnsavedChangesContextType = {
  /**
   * Request navigation to a path or typed destination. If there are unsaved changes,
   * shows a confirmation modal. Otherwise, navigates immediately.
   */
  requestNavigation: (target: NavigationTarget) => void
  /**
   * Register the save handler from BuilderContent
   */
  registerSaveHandler: (handler: () => Promise<boolean>) => void
  /**
   * Unregister the save handler when BuilderContent unmounts
   */
  unregisterSaveHandler: () => void
  /**
   * Register a dirty check for the current page. The provider calls this function
   * before navigating to determine if a confirmation modal is needed.
   * Returns an unregister function.
   */
  registerDirtyCheck: (options: DirtyCheckOptions) => () => void
}

export const UnsavedChangesContext = createContext<UnsavedChangesContextType | null>(null)
