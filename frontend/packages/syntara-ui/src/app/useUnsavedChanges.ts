import { useNavigate } from '@tanstack/react-router'
import { use, useMemo } from 'react'

import {
  UnsavedChangesContext,
  type UnsavedChangesContextType,
} from '../providers/unsaved-changes/unsavedChangesContext'
import { detachPromise } from '../utils/detachPromise'

import { navigateToTarget, type NavigationTarget } from './typedRouteDestinations'

const noop = () => () => {}

export function useUnsavedChanges(): UnsavedChangesContextType {
  const context = use(UnsavedChangesContext)
  const navigate = useNavigate()

  const fallback = useMemo<UnsavedChangesContextType>(
    () => ({
      requestNavigation: (target: NavigationTarget) => detachPromise(navigateToTarget(navigate, target)),
      registerSaveHandler: noop,
      unregisterSaveHandler: () => {},
      registerDirtyCheck: noop,
    }),
    [navigate]
  )

  return context ?? fallback
}
