import { useCallback, useState, type Dispatch } from 'react'

import type { BuilderAction } from '../builderReducer'

export function useVersionViewNavigation(options: {
  isDirty: boolean
  isViewingVersion: boolean
  canSave: boolean
  dispatch: Dispatch<BuilderAction>
  handleSaveWorkflow: () => Promise<boolean>
  searchParams: URLSearchParams
  setSearchParams: (params: URLSearchParams) => void
}) {
  const { isDirty, isViewingVersion, canSave, dispatch, handleSaveWorkflow, searchParams, setSearchParams } = options
  const [pendingViewVersion, setPendingViewVersion] = useState<number | null>(null)

  const setVersionParam = useCallback(
    (version: number) => {
      const params = new URLSearchParams(searchParams)
      params.set('version', String(version))
      setSearchParams(params)
    },
    [searchParams, setSearchParams]
  )

  const onSelectVersion = useCallback(
    (version: number) => {
      if (isDirty && !isViewingVersion) {
        setPendingViewVersion(version)
      } else {
        dispatch({ type: 'SET_VIEWING_VERSION', payload: version })
        setVersionParam(version)
      }
    },
    [isDirty, isViewingVersion, dispatch, setVersionParam]
  )

  const onSave = useCallback(async (): Promise<boolean> => {
    const versionToView = pendingViewVersion
    if (!canSave || versionToView === null || !(await handleSaveWorkflow())) return false
    setPendingViewVersion(null)
    dispatch({ type: 'SET_VIEWING_VERSION', payload: versionToView })
    setVersionParam(versionToView)
    return true
  }, [canSave, pendingViewVersion, handleSaveWorkflow, dispatch, setVersionParam])

  const onViewWithoutSaving = useCallback(() => {
    if (pendingViewVersion !== null) {
      dispatch({ type: 'SET_VIEWING_VERSION', payload: pendingViewVersion })
      setVersionParam(pendingViewVersion)
    }
    setPendingViewVersion(null)
  }, [pendingViewVersion, dispatch, setVersionParam])

  return {
    onSelectVersion,
    saveBeforeViewDialog: {
      isOpen: pendingViewVersion !== null,
      onSave,
      onViewWithoutSaving,
      onCancel: () => setPendingViewVersion(null),
    },
  }
}
