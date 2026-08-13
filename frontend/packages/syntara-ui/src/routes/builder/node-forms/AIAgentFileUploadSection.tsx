import { useCallback, useEffect, useRef, useState } from 'react'

import {
  FILE_STORAGE_UNAVAILABLE_MESSAGE,
  FILE_STORAGE_UNCONFIGURED_MESSAGE,
  useFileStorageStatus,
} from '../../../hooks/useFileStorageStatus'
import { useAlerts } from '../../../providers/alerts'
import { detachPromise } from '../../../utils/detachPromise'
import { downloadFileById } from '../../../utils/downloadFile'
import { FileUpload } from '../components/file-upload'

import nodeFormStyles from './shared/nodeFormStyles.module.css'
import { useFileUploadState, type FileContextType } from './useFileUploadState'

type AIAgentFileUploadSectionProps = Readonly<{
  projectId: string
  isVersionView: boolean
  hasExistingFiles: boolean
  fileContext: FileContextType
}>

export function AIAgentFileUploadSection({
  projectId,
  isVersionView,
  hasExistingFiles,
  fileContext,
}: AIAgentFileUploadSectionProps) {
  const { uploadedFiles, handleFilesSelected, handleFileRemove, deletingFileIds, markPersisted } = useFileUploadState(
    fileContext,
    projectId
  )
  const { isConfigured: isFileStorageConfigured, status: fileStorageStatus } = useFileStorageStatus()
  const { showSuccess, showError } = useAlerts()
  const [downloadingFileIds, setDownloadingFileIds] = useState<Set<string>>(() => new Set())
  const downloadControllersRef = useRef(new Map<string, AbortController>())
  const onMarkPersistedReady = fileContext.onMarkPersistedReady

  useEffect(() => {
    onMarkPersistedReady?.(markPersisted)
    return () => {
      onMarkPersistedReady?.(null)
    }
  }, [markPersisted, onMarkPersistedReady])

  const clearDownloadState = useCallback((fileId: string) => {
    downloadControllersRef.current.delete(fileId)
    setDownloadingFileIds((prev) => {
      if (!prev.has(fileId)) return prev
      const next = new Set(prev)
      next.delete(fileId)
      return next
    })
  }, [])

  const handleFileDownload = useCallback(
    (fileId: string, fileName: string) => {
      if (downloadControllersRef.current.has(fileId)) return

      const controller = new AbortController()
      downloadControllersRef.current.set(fileId, controller)
      setDownloadingFileIds((prev) => new Set(prev).add(fileId))

      detachPromise(
        downloadFileById(fileId, fileName, controller.signal)
          .then((downloadedName) => {
            showSuccess({ title: `${downloadedName} downloaded successfully.` })
          })
          .catch((error: unknown) => {
            if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) {
              return
            }
            showError({ title: `Unable to download ${fileName}. Please try again.` })
          })
          .finally(() => {
            clearDownloadState(fileId)
          })
      )
    },
    [clearDownloadState, showError, showSuccess]
  )

  const handleFileDownloadCancel = useCallback((fileId: string) => {
    downloadControllersRef.current.get(fileId)?.abort()
  }, [])

  const isUploadDisabled = isVersionView || !isFileStorageConfigured
  const disabledTooltip = (() => {
    if (isVersionView) return undefined
    if (fileStorageStatus === 'unconfigured') return FILE_STORAGE_UNCONFIGURED_MESSAGE
    return FILE_STORAGE_UNAVAILABLE_MESSAGE
  })()

  return (
    <fieldset className={nodeFormStyles.disabledFieldset}>
      <FileUpload
        files={uploadedFiles}
        onFilesSelected={handleFilesSelected}
        onFileRemove={handleFileRemove}
        onFileDownload={handleFileDownload}
        onFileDownloadCancel={handleFileDownloadCancel}
        downloadingFileIds={downloadingFileIds}
        deletingFileIds={deletingFileIds}
        canRemove={!isVersionView}
        acceptedMimeTypes={['.pdf', '.doc', '.docx', '.txt', '.md']}
        aria-label="Context file upload"
        disabled={isUploadDisabled}
        disabledTooltip={disabledTooltip}
        defaultStatusExpanded={!hasExistingFiles}
      />
    </fieldset>
  )
}
