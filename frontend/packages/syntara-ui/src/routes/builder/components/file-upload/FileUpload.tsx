import {
  type DropEvent,
  ExpandableSection,
  HelperText,
  HelperTextItem,
  Icon,
  MultipleFileUpload,
  MultipleFileUploadMain,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiSyncIcon, RhUiUploadIcon } from '@patternfly/react-icons'
import { useCallback, useState } from 'react'

import { generateUUID } from '../../../../utils/generateUUID'

import styles from './FileUpload.module.css'
import { FileUploadItem, type FileUploadItemProps } from './FileUploadItem'
import {
  computeUploadStatusProps,
  createDropRejectedHandler,
  formatAcceptedTypesForDisplay,
  type UploadedFile,
} from './fileUploadUtils'

export type { UploadedFile } from './fileUploadUtils'

export type FileUploadProps = {
  onFilesSelected?: (files: File[]) => void
  onFileRemove?: (fileId: string) => void
  /** Called when the user downloads a successfully uploaded file. */
  onFileDownload?: (fileId: string, fileName: string) => void
  /** Called when the user cancels an in-progress download for a file. */
  onFileDownloadCancel?: (fileId: string) => void
  /** File ids currently being downloaded (shows spinner on each card's download action). */
  downloadingFileIds?: ReadonlySet<string>
  /** File ids currently being deleted from the server (shows spinner on each card's remove action). */
  deletingFileIds?: ReadonlySet<string>
  /** When false, hides the remove action on file cards. Default: true. */
  canRemove?: boolean
  maxFiles?: number
  maxSizeBytes?: number
  maxSizeMB?: number
  acceptedMimeTypes?: string[]
  files?: UploadedFile[]
  titleText?: string
  infoText?: string
  browseButtonText?: string
  className?: string
  'aria-label'?: string
  /** When true, disables the dropzone and file input, preventing file selection. */
  disabled?: boolean
  /** Tooltip text shown when hovering over the disabled dropzone. Only displayed when `disabled` is true. */
  disabledTooltip?: string
  /** When false, the file list starts collapsed. Default: true. */
  defaultStatusExpanded?: boolean
}

function formatAcceptProp(acceptedMimeTypes?: string[]): Record<string, string[]> | undefined {
  if (!acceptedMimeTypes || acceptedMimeTypes.length === 0) {
    return undefined
  }

  const acceptObj: Record<string, string[]> = {}
  for (const type of acceptedMimeTypes) {
    if (type.startsWith('.')) {
      acceptObj['application/octet-stream'] = acceptObj['application/octet-stream'] || []
      acceptObj['application/octet-stream'].push(type)
    } else {
      acceptObj[type] = acceptObj[type] || []
    }
  }
  return acceptObj
}

function UploadStatusToggle({ variant, text }: { variant: 'danger' | 'success' | 'inProgress'; text?: string }) {
  switch (variant) {
    case 'danger':
      return (
        <>
          <Icon status="danger">
            <RhUiCloseCircleIcon />
          </Icon>{' '}
          {text}
        </>
      )
    case 'success':
      return (
        <>
          <Icon status="success">
            <RhUiCheckCircleIcon />
          </Icon>{' '}
          {text}
        </>
      )
    case 'inProgress':
      return (
        <>
          <Icon>
            <RhUiSyncIcon />
          </Icon>{' '}
          {text}
        </>
      )
  }
}

const EMPTY_DOWNLOADING_FILE_IDS: ReadonlySet<string> = new Set()
const EMPTY_DELETING_FILE_IDS: ReadonlySet<string> = new Set()

export function FileUpload({
  onFilesSelected,
  onFileRemove,
  onFileDownload,
  onFileDownloadCancel,
  downloadingFileIds = EMPTY_DOWNLOADING_FILE_IDS,
  deletingFileIds = EMPTY_DELETING_FILE_IDS,
  canRemove = true,
  maxFiles,
  maxSizeBytes,
  maxSizeMB,
  acceptedMimeTypes,
  files: controlledFiles,
  titleText = 'Drag and drop files here',
  infoText,
  browseButtonText = 'Upload',
  className,
  disabled = false,
  disabledTooltip,
  defaultStatusExpanded = true,
}: FileUploadProps) {
  const [internalFiles, setInternalFiles] = useState<UploadedFile[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isStatusExpanded, setIsStatusExpanded] = useState(defaultStatusExpanded)
  const handleToggleStatus = useCallback(() => {
    setIsStatusExpanded((prev) => !prev)
  }, [])

  const uploadedFiles = controlledFiles ?? internalFiles
  const isControlled = controlledFiles !== undefined
  const effectiveMaxSizeBytes = maxSizeBytes ?? (maxSizeMB !== undefined ? maxSizeMB * 1024 * 1024 : undefined)
  const handleDropRejected = createDropRejectedHandler({
    setErrorMessage,
    effectiveMaxSizeBytes,
    acceptedMimeTypes,
    maxFiles,
  })

  const handleFileDrop = (_event: DropEvent, droppedFiles: File[]) => {
    setErrorMessage(null)
    if (droppedFiles.length === 0) return
    setIsStatusExpanded(true)

    const currentFileNames = new Set(uploadedFiles.map((f) => f.file.name))
    const reUploadNames = new Set(droppedFiles.filter((file) => currentFileNames.has(file.name)).map((f) => f.name))

    const newFiles: UploadedFile[] = droppedFiles.map((file) => ({
      id: generateUUID(),
      file,
      progress: 0,
      status: 'pending' as const,
    }))

    if (!isControlled) {
      setInternalFiles((prev) => [...prev.filter((f) => !reUploadNames.has(f.file.name)), ...newFiles])
    }
    onFilesSelected?.(droppedFiles)
  }

  const handleFileRemove = (fileId: string) => {
    setErrorMessage(null)
    if (!isControlled) {
      setInternalFiles((prev) => prev.filter((f) => f.id !== fileId))
    }
    onFileRemove?.(fileId)
  }

  const dropzoneProps = {
    accept: formatAcceptProp(acceptedMimeTypes),
    maxSize: effectiveMaxSizeBytes,
    maxFiles: maxFiles,
    onDropRejected: handleDropRejected,
    disabled,
  }

  const { statusToggleText, statusToggleIcon } = computeUploadStatusProps(uploadedFiles)
  const acceptedTypesDisplay = formatAcceptedTypesForDisplay(acceptedMimeTypes)
  const resolvedInfoText =
    infoText ?? (acceptedTypesDisplay ? `Accepted file types: ${acceptedTypesDisplay}` : undefined)

  let resolvedClassName = className
  if (disabled) {
    resolvedClassName = className ? `${className} ${styles.disabled}` : styles.disabled
  }

  const fileUploadContent = (
    <MultipleFileUpload onFileDrop={handleFileDrop} dropzoneProps={dropzoneProps} className={resolvedClassName}>
      <MultipleFileUploadMain
        titleIcon={<RhUiUploadIcon />}
        titleText={titleText}
        titleTextSeparator="or"
        infoText={resolvedInfoText}
        browseButtonText={browseButtonText}
      />
      {errorMessage && (
        <HelperText>
          <HelperTextItem variant="error">{errorMessage}</HelperTextItem>
        </HelperText>
      )}
      {uploadedFiles.length > 0 && (
        <ExpandableSection
          toggleContent={<UploadStatusToggle variant={statusToggleIcon} text={statusToggleText} />}
          isExpanded={isStatusExpanded}
          onToggle={handleToggleStatus}
          toggleAriaLabel="Toggle file list"
        >
          {uploadedFiles.map((uploadedFile) => (
            <FileUploadItem
              key={uploadedFile.id}
              file={uploadedFile.file}
              fileId={uploadedFile.id}
              fileSize={uploadedFile.fileSize}
              status={uploadedFile.status}
              progress={uploadedFile.progress}
              errorMessage={uploadedFile.errorMessage}
              onRemove={canRemove ? () => handleFileRemove(uploadedFile.id) : undefined}
              onDownload={onFileDownload ? () => onFileDownload(uploadedFile.id, uploadedFile.file.name) : undefined}
              onCancelDownload={onFileDownloadCancel ? () => onFileDownloadCancel(uploadedFile.id) : undefined}
              isDownloading={downloadingFileIds.has(uploadedFile.id)}
              isDeleting={deletingFileIds.has(uploadedFile.id)}
              downloadButtonAriaLabel={`Download ${uploadedFile.file.name}`}
              cancelDownloadAriaLabel={`Cancel download of ${uploadedFile.file.name}`}
              removeButtonAriaLabel={`Remove ${uploadedFile.file.name}`}
            />
          ))}
        </ExpandableSection>
      )}
    </MultipleFileUpload>
  )

  if (disabled && disabledTooltip) {
    return (
      <Tooltip content={disabledTooltip}>
        <div>{fileUploadContent}</div>
      </Tooltip>
    )
  }

  return fileUploadContent
}

export type { FileUploadItemProps }
