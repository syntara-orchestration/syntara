import { useCallback, useState } from 'react'

import { useFileUploadWithProgress } from '../../../hooks/useFileUploadWithProgress'
import { useAlerts } from '../../../providers/alerts'
import { deleteFileById } from '../../../utils/deleteFile'
import { detachPromise } from '../../../utils/detachPromise'
import { generateUUID } from '../../../utils/generateUUID'
import type { UploadedFile } from '../components/file-upload'

export type FileContextType = {
  completedFiles: UploadedFile[]
  addFiles: (files: UploadedFile[]) => void
  removeFile: (fileId: string) => void
  removeFilesByName: (names: Set<string>) => void
  isFilesError: boolean
}

export function useFileUploadState(fileContext: FileContextType, projectId: string) {
  const { completedFiles, addFiles, removeFile, removeFilesByName } = fileContext
  const [uploadingFiles, setUploadingFiles] = useState<UploadedFile[]>([])
  const [deletingFileIds, setDeletingFileIds] = useState<Set<string>>(() => new Set())
  /** Server file IDs uploaded during this editing session — safe to hard-delete on remove/replace. */
  const [sessionUploadedIds, setSessionUploadedIds] = useState<Set<string>>(() => new Set())
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

  const clearDeletingState = useCallback((fileId: string) => {
    setDeletingFileIds((prev) => {
      if (!prev.has(fileId)) return prev
      const next = new Set(prev)
      next.delete(fileId)
      return next
    })
  }, [])

  const clearSessionUploadId = useCallback((fileId: string) => {
    setSessionUploadedIds((prev) => {
      if (!prev.has(fileId)) return prev
      const next = new Set(prev)
      next.delete(fileId)
      return next
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

  const deleteSessionBlob = useCallback(
    (fileId: string, fileName: string, onSuccess?: () => void) => {
      setDeletingFileIds((prev) => new Set(prev).add(fileId))
      detachPromise(
        deleteFileById(fileId)
          .then(() => {
            onSuccess?.()
          })
          .catch(() => {
            showError({ title: `Unable to delete ${fileName}. Please try again.` })
          })
          .finally(() => {
            clearDeletingState(fileId)
          })
      )
    },
    [showError, clearDeletingState]
  )

  const handleFilesSelected = useCallback(
    (files: File[]) => {
      const reUploadNames = new Set(files.map((f) => f.name))
      const newFiles: UploadedFile[] = files.map((file) => ({
        id: generateUUID(),
        file,
        progress: 0,
        status: 'uploading' as const,
      }))

      // Same-name replace: hard-delete only session uploads; hydrated attachments detach locally.
      for (const file of completedFiles) {
        if (reUploadNames.has(file.file.name) && file.status === 'success' && sessionUploadedIds.has(file.id)) {
          deleteSessionBlob(file.id, file.file.name)
        }
      }

      removeFilesByName(reUploadNames)
      for (const file of completedFiles) {
        if (reUploadNames.has(file.file.name)) {
          clearSessionUploadId(file.id)
        }
      }
      setUploadingFiles(newFiles)

      const upload = async () => {
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
      }

      detachPromise(upload())
    },
    [
      projectId,
      uploadFiles,
      addFiles,
      removeFilesByName,
      completedFiles,
      sessionUploadedIds,
      deleteSessionBlob,
      clearSessionUploadId,
    ]
  )

  const handleFileRemove = useCallback(
    (fileId: string) => {
      if (deletingFileIds.has(fileId)) return

      const target = completedFiles.find((f) => f.id === fileId) ?? uploadingFiles.find((f) => f.id === fileId)
      // Only hard-delete blobs uploaded in this session. Hydrated existing attachments
      // are detached from form state only so other versions/nodes keep their references.
      const shouldDeleteFromServer = target?.status === 'success' && sessionUploadedIds.has(fileId)

      if (!shouldDeleteFromServer) {
        removeLocalFile(fileId)
        return
      }

      const fileName = target.file.name
      deleteSessionBlob(fileId, fileName, () => {
        removeLocalFile(fileId)
        showSuccess({ title: `${fileName} deleted successfully.` })
      })
    },
    [
      completedFiles,
      uploadingFiles,
      deletingFileIds,
      sessionUploadedIds,
      removeLocalFile,
      deleteSessionBlob,
      showSuccess,
    ]
  )

  return { uploadedFiles, handleFilesSelected, handleFileRemove, deletingFileIds }
}
