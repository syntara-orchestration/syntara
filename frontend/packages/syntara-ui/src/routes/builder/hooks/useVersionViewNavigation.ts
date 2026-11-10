import { useCallback, useState, type Dispatch } from 'react'

import type { BuilderAction } from '../builderReducer'

export function useVersionViewNavigation(options: {
  isDirty: boolean
  isViewingVersion: boolean
  dispatch: Dispatch<BuilderAction>
  handleSaveWorkflow: () => Promise<boolean>
  setVersionParam: (version: number) => void
}) {
  const { isDirty, isViewingVersion, dispatch, handleSaveWorkflow, setVersionParam } = options
  const [pendingViewVersion, setPendingViewVersion] = useState<number | null>(null)

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
    const saved = await handleSaveWorkflow()
    setPendingViewVersion(null)
    if (saved && versionToView !== null) {
      dispatch({ type: 'SET_VIEWING_VERSION', payload: versionToView })
      setVersionParam(versionToView)
    }
    return saved
  }, [pendingViewVersion, handleSaveWorkflow, dispatch, setVersionParam])

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
