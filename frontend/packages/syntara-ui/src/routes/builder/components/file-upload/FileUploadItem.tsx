import {
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Progress,
  ProgressSize,
  Truncate,
} from '@patternfly/react-core'
import { RhUiDocumentFillIcon, RhUiDownloadIcon, RhUiTrashIcon } from '@patternfly/react-icons'

import styles from './FileUploadItem.module.css'

export type FileUploadItemProps = {
  file: File
  fileId: string
  fileSize?: number
  status?: 'pending' | 'uploading' | 'success' | 'error'
  progress?: number
  errorMessage?: string
  fileName?: string
  onRemove?: () => void
  onDownload?: () => void
  onCancelDownload?: () => void
  isDownloading?: boolean
  isDeleting?: boolean
  className?: string
  removeButtonAriaLabel?: string
  downloadButtonAriaLabel?: string
  cancelDownloadAriaLabel?: string
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getFileExtension(filename: string): string {
  const ext = filename.split('.').pop()?.toUpperCase()
  return ext ?? 'FILE'
}

function getProgressVariant(isError: boolean, isSuccess: boolean) {
  if (isError) return 'danger' as const
  if (isSuccess) return 'success' as const
  return undefined
}

function getFileUploadItemActionVisibility({
  onDownload,
  onCancelDownload,
  onRemove,
  isSuccess,
  isDownloading,
  isDeleting,
}: {
  onDownload?: () => void
  onCancelDownload?: () => void
  onRemove?: () => void
  isSuccess: boolean
  isDownloading: boolean
  isDeleting: boolean
}) {
  // Hide download while a delete is in progress (delete occupies that action slot).
  const showDownload = Boolean(onDownload) && isSuccess && !isDeleting
  const showCancelDownload = showDownload && isDownloading && Boolean(onCancelDownload)
  // Hide delete while a download is in progress (download occupies that action slot).
  const showRemove = Boolean(onRemove) && !isDownloading
  return { showDownload, showCancelDownload, showRemove }
}

type FileUploadItemActionsProps = Readonly<{
  showDownload: boolean
  showCancelDownload: boolean
  showRemove: boolean
  isDownloading: boolean
  isDeleting: boolean
  onDownload?: () => void
  onCancelDownload?: () => void
  onRemove?: () => void
  downloadButtonAriaLabel: string
  cancelDownloadAriaLabel: string
  removeButtonAriaLabel: string
}>

function FileUploadItemActions({
  showDownload,
  showCancelDownload,
  showRemove,
  isDownloading,
  isDeleting,
  onDownload,
  onCancelDownload,
  onRemove,
  downloadButtonAriaLabel,
  cancelDownloadAriaLabel,
  removeButtonAriaLabel,
}: FileUploadItemActionsProps) {
  if (!showDownload && !showCancelDownload && !showRemove) return null

  return (
    <FlexItem>
      <Flex spaceItems={{ default: 'spaceItemsSm' }} alignItems={{ default: 'alignItemsCenter' }}>
        {showDownload && (
          <FlexItem>
            <Button
              variant="plain"
              aria-label={downloadButtonAriaLabel}
              onClick={onDownload}
              size="sm"
              isLoading={isDownloading}
              isDisabled={isDownloading || isDeleting}
            >
              <RhUiDownloadIcon />
            </Button>
          </FlexItem>
        )}
        {showCancelDownload && (
          <FlexItem>
            <Button variant="link" isInline onClick={onCancelDownload} aria-label={cancelDownloadAriaLabel}>
              Cancel
            </Button>
          </FlexItem>
        )}
        {showRemove && (
          <FlexItem>
            <Button
              variant="plain"
              aria-label={removeButtonAriaLabel}
              onClick={onRemove}
              size="sm"
              isLoading={isDeleting}
              isDisabled={isDeleting}
            >
              <RhUiTrashIcon />
            </Button>
          </FlexItem>
        )}
      </Flex>
    </FlexItem>
  )
}

export function FileUploadItem({
  file,
  fileSize,
  status = 'pending',
  progress,
  errorMessage,
  fileName,
  onRemove,
  onDownload,
  onCancelDownload,
  isDownloading = false,
  isDeleting = false,
  className,
  removeButtonAriaLabel = 'Remove file',
  downloadButtonAriaLabel = 'Download file',
  cancelDownloadAriaLabel = 'Cancel download',
}: FileUploadItemProps) {
  const displayName = fileName ?? file.name
  const isError = status === 'error'
  const isSuccess = status === 'success'
  const fileExtension = getFileExtension(file.name)
  const { showDownload, showCancelDownload, showRemove } = getFileUploadItemActionVisibility({
    onDownload,
    onCancelDownload,
    onRemove,
    isSuccess,
    isDownloading,
    isDeleting,
  })
  const showProgress = progress !== undefined && status !== 'pending'
  const itemClassName = className ? `${styles.item} ${className}` : styles.item

  return (
    <div className={itemClassName}>
      <Flex alignItems={{ default: 'alignItemsCenter' }}>
        <FlexItem>
          <RhUiDocumentFillIcon className={isError ? `${styles.fileIcon} ${styles.fileIconError}` : styles.fileIcon} />
        </FlexItem>
        <FlexItem flex={{ default: 'flex_1' }} className={styles.fileInfo}>
          <Content
            component={ContentVariants.p}
            className={isError ? `${styles.fileName} ${styles.fileNameError}` : styles.fileName}
          >
            <Truncate content={displayName} position="middle" />
          </Content>
          <Content component={ContentVariants.small} className={styles.fileMeta}>
            {fileExtension} | {formatFileSize(fileSize ?? file.size)}
            {isError && errorMessage && ` - ${errorMessage}`}
          </Content>
        </FlexItem>
        <FileUploadItemActions
          showDownload={showDownload}
          showCancelDownload={showCancelDownload}
          showRemove={showRemove}
          isDownloading={isDownloading}
          isDeleting={isDeleting}
          onDownload={onDownload}
          onCancelDownload={onCancelDownload}
          onRemove={onRemove}
          downloadButtonAriaLabel={downloadButtonAriaLabel}
          cancelDownloadAriaLabel={cancelDownloadAriaLabel}
          removeButtonAriaLabel={removeButtonAriaLabel}
        />
      </Flex>

      {showProgress && (
        <div className={styles.progress}>
          <Progress
            value={progress}
            size={ProgressSize.sm}
            variant={getProgressVariant(isError, isSuccess)}
            measureLocation="outside"
            aria-label={`${displayName} upload progress`}
          />
        </div>
      )}
    </div>
  )
}
