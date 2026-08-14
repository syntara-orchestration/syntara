import { useCallback, useRef, useState } from 'react'

import { useFileUploadWithProgress } from '../../../hooks/useFileUploadWithProgress'
import { useAlerts } from '../../../providers/alerts'
import { deleteFileById } from '../../../utils/deleteFile'
import { detachPromise } from '../../../utils/detachPromise'
import { generateUUID } from '../../../utils/generateUUID'
import type { UploadedFile } from '../components/file-upload'

export type MarkPersistedFn = (fileIds?: Iterable<string>) => void

export type FileContextType = {
  completedFiles: UploadedFile[]
  addFiles: (files: UploadedFile[]) => void
  removeFile: (fileId: string) => void
  removeFilesByName: (names: Set<string>) => void
  isFilesError: boolean
  /**
   * Called by the upload section to register/unregister markPersisted so the form
   * can clear session-upload tracking after file IDs enter durable node state.
   */
  onMarkPersistedReady?: (fn: MarkPersistedFn | null) => void
  /**
   * Called whenever the set of file IDs with in-flight DELETEs changes.
   * The form uses this to exclude mid-DELETE files from submit payloads.
   */
  onDeletingFileIdsChange?: (ids: Set<string>) => void
}

export function useFileUploadState(fileContext: FileContextType, projectId: string) {
  const { completedFiles, addFiles, removeFile, removeFilesByName } = fileContext
  const [uploadingFiles, setUploadingFiles] = useState<UploadedFile[]>([])
  const [deletingFileIds, setDeletingFileIds] = useState<Set<string>>(() => new Set())
  /**
   * Server file IDs uploaded during this editing session and not yet persisted into
   * durable node/workflow state. Only these are safe to hard-delete on remove/replace.
   * After persist, membership is cleared so remove becomes detach-only (like hydrated).
   */
  const [sessionUploadedIds, setSessionUploadedIds] = useState<Set<string>>(() => new Set())
  /** Synchronous in-flight DELETE guard — state alone can miss double-clicks before re-render. */
  const deletingFileIdsRef = useRef<Set<string>>(new Set())
  /** Prevent overlapping select/replace pipelines from interleaving DELETEs and UI clears. */
  const selectionInFlightRef = useRef(false)
  /** Stable ref for the external callback so beginDeleting/clearDeletingState can notify synchronously. */
  const onDeletingFileIdsChangeRef = useRef(fileContext.onDeletingFileIdsChange)
  onDeletingFileIdsChangeRef.current = fileContext.onDeletingFileIdsChange
  const { uploadFiles, progress, error } = useFileUploadWithProgress()
  const { showSuccess, showError } = useAlerts()

  const uploadedFiles: UploadedFile[] = [
    ...completedFiles,
    ...uploadingFiles.map((f) => {
      const fileProgress = progress.find((p) => p.fileName === f.file.name)
      return {
        ...f,
        progress: fileProgress?.percentage ?? f.progress,
        status: error ? ('error' as const) : f.status,
        errorMessage: error?.message ?? f.errorMessage,
      }
    }),
  ]

  const beginDeleting = useCallback((fileId: string): boolean => {
    if (deletingFileIdsRef.current.has(fileId)) return false
    deletingFileIdsRef.current.add(fileId)
    const next = new Set(deletingFileIdsRef.current)
    setDeletingFileIds(next)
    onDeletingFileIdsChangeRef.current?.(next)
    return true
  }, [])

  const clearDeletingState = useCallback((fileId: string) => {
    deletingFileIdsRef.current.delete(fileId)
    const next = new Set(deletingFileIdsRef.current)
    setDeletingFileIds(next)
    onDeletingFileIdsChangeRef.current?.(next)
  }, [])

  const clearSessionUploadId = useCallback((fileId: string) => {
    setSessionUploadedIds((prev) => {
      if (!prev.has(fileId)) return prev
      const next = new Set(prev)
      next.delete(fileId)
      return next
    })
  }, [])

  const markPersisted = useCallback<MarkPersistedFn>((fileIds) => {
    setSessionUploadedIds((prev) => {
      if (prev.size === 0) return prev
      if (fileIds === undefined) {
        return new Set()
      }
      let changed = false
      const next = new Set(prev)
      for (const id of fileIds) {
        if (next.delete(id)) changed = true
      }
      return changed ? next : prev
    })
  }, [])

  const removeLocalFile = useCallback(
    (fileId: string) => {
      removeFile(fileId)
      setUploadingFiles((prev) => prev.filter((f) => f.id !== fileId))
      clearSessionUploadId(fileId)
    },
    [removeFile, clearSessionUploadId]
  )

  /**
   * Awaitable DELETE for a session blob. Returns true only on success.
   * IMPORTANT: does NOT clear deletingState — callers must call clearDeletingState
   * after removeLocalFile so the file never appears "live" between S3 delete and
   * UI removal (prevents auto-submit from persisting a deleted blob reference).
   */
  const deleteSessionBlob = useCallback(
    async (fileId: string, fileName: string): Promise<boolean> => {
      if (!beginDeleting(fileId)) {
        return false
      }
      try {
        await deleteFileById(fileId)
        return true
      } catch {
        showError({ title: `Unable to delete ${fileName}. Please try again.` })
        clearDeletingState(fileId)
        return false
      }
    },
    [showError, beginDeleting, clearDeletingState]
  )

  const handleFilesSelected = useCallback(
    (files: File[]) => {
      if (selectionInFlightRef.current) {
        showError({ title: 'A file upload is already in progress. Please wait.' })
        return
      }
      selectionInFlightRef.current = true

      detachPromise(
        (async () => {
          try {
            const reUploadNames = new Set(files.map((f) => f.name))

            // Same-name replace: await DELETE for session uploads before touching UI / starting upload.
            // Hydrated / persisted attachments with the same name are detached locally only (no DELETE).
            const sessionReplacements = completedFiles.filter(
              (file) =>
                reUploadNames.has(file.file.name) && file.status === 'success' && sessionUploadedIds.has(file.id)
            )

            // Avoid racing a remove-in-flight DELETE (would double-DELETE / confuse UI).
            if (sessionReplacements.some((file) => deletingFileIdsRef.current.has(file.id))) {
              showError({
                title: 'A file delete is already in progress. Please try again.',
              })
              return
            }

            // Mark ALL session replacements as deleting up front so every chip in
            // the batch shows the spinner immediately, not just the one currently
            // being deleted.
            for (const file of sessionReplacements) {
              beginDeleting(file.id)
            }

            // Sequential DELETEs; defer all UI clears until the batch succeeds.
            // On first failure: stop further DELETEs, unlock remaining + successes, inform user, abort upload.
            const deletedSuccessfully: UploadedFile[] = []
            for (let i = 0; i < sessionReplacements.length; i++) {
              const file = sessionReplacements[i]
              try {
                await deleteFileById(file.id)
                deletedSuccessfully.push(file)
              } catch {
                showError({ title: `Unable to delete ${file.file.name}. Please try again.` })
                clearDeletingState(file.id)
                for (let j = i + 1; j < sessionReplacements.length; j++) {
                  clearDeletingState(sessionReplacements[j].id)
                }
                for (const removed of deletedSuccessfully) {
                  removeLocalFile(removed.id)
                  clearDeletingState(removed.id)
                }
                if (deletedSuccessfully.length > 0) {
                  const names = deletedSuccessfully.map((f) => f.file.name).join(', ')
                  showError({
                    title: `Replace aborted. ${names} ${deletedSuccessfully.length === 1 ? 'was' : 'were'} already removed.`,
                  })
                }
                return
              }
            }

            for (const file of deletedSuccessfully) {
              removeLocalFile(file.id)
              clearDeletingState(file.id)
            }

            removeFilesByName(reUploadNames)
            for (const file of completedFiles) {
              if (reUploadNames.has(file.file.name)) {
                clearSessionUploadId(file.id)
              }
            }

            const newFiles: UploadedFile[] = files.map((file) => ({
              id: generateUUID(),
              file,
              progress: 0,
              status: 'uploading' as const,
            }))
            setUploadingFiles(newFiles)

            try {
              const response = await uploadFiles(files, projectId)
              const successFiles = newFiles.map((f, i) => ({
                ...f,
                id: response.files?.[i]?.file_id ?? f.id,
                progress: 100,
                status: 'success' as const,
              }))
              addFiles(successFiles)
              setSessionUploadedIds((prev) => {
                const next = new Set(prev)
                for (const f of successFiles) next.add(f.id)
                return next
              })
              setUploadingFiles([])
            } catch {
              const errorFiles = newFiles.map((f) => ({
                ...f,
                status: 'error' as const,
                errorMessage: 'Upload failed. Please try again.',
              }))
              addFiles(errorFiles)
              setUploadingFiles([])
            }
          } finally {
            selectionInFlightRef.current = false
          }
        })()
      )
    },
    [
      projectId,
      uploadFiles,
      addFiles,
      removeFilesByName,
      completedFiles,
      sessionUploadedIds,
      beginDeleting,
      clearDeletingState,
      clearSessionUploadId,
      removeLocalFile,
      showError,
    ]
  )

  const handleFileRemove = useCallback(
    (fileId: string) => {
      // Sync ref guard — do not rely on deletingFileIds state (stale until re-render).
      if (deletingFileIdsRef.current.has(fileId)) return
      // Block manual remove while a replace pipeline is running to avoid aborting the batch.
      if (selectionInFlightRef.current) {
        showError({ title: 'A file replace is in progress. Please try again.' })
        return
      }

      const target = completedFiles.find((f) => f.id === fileId) ?? uploadingFiles.find((f) => f.id === fileId)
      // Only hard-delete blobs still in the session set (uploaded here, not yet persisted).
      // Hydrated / post-persist attachments are detach-only so durable refs stay valid.
      const shouldDeleteFromServer = target?.status === 'success' && sessionUploadedIds.has(fileId)

      if (!shouldDeleteFromServer) {
        removeLocalFile(fileId)
        return
      }

      const fileName = target.file.name
      detachPromise(
        (async () => {
          const deleted = await deleteSessionBlob(fileId, fileName)
          if (!deleted) return
          removeLocalFile(fileId)
          clearDeletingState(fileId)
          showSuccess({ title: `${fileName} deleted successfully.` })
        })()
      )
    },
    [
      completedFiles,
      uploadingFiles,
      sessionUploadedIds,
      removeLocalFile,
      deleteSessionBlob,
      clearDeletingState,
      showError,
      showSuccess,
    ]
  )

  return { uploadedFiles, handleFilesSelected, handleFileRemove, deletingFileIds, markPersisted }
}
