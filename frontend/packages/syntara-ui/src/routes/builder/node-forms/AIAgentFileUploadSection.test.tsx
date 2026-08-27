import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import {
  FILE_STORAGE_UNAVAILABLE_MESSAGE,
  FILE_STORAGE_UNCONFIGURED_MESSAGE,
  useFileStorageStatus,
} from '../../../hooks/useFileStorageStatus'
import { useFileUploadWithProgress } from '../../../hooks/useFileUploadWithProgress'
import { useAlerts } from '../../../providers/alerts'
import { downloadFileById } from '../../../utils/downloadFile'
import type { UploadedFile } from '../components/file-upload'

import { AIAgentFileUploadSection } from './AIAgentFileUploadSection'
import type { FileContextType } from './useFileUploadState'

vi.mock('../../../hooks/useFileStorageStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../hooks/useFileStorageStatus')>()),
  useFileStorageStatus: vi.fn(),
}))

vi.mock('../../../hooks/useFileUploadWithProgress', () => ({
  useFileUploadWithProgress: vi.fn(),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(),
}))

vi.mock('../../../utils/downloadFile', () => ({
  downloadFileById: vi.fn(),
}))

vi.mock('../../../utils/deleteFile', () => ({
  deleteFileById: vi.fn(() => Promise.resolve()),
}))

vi.mock('../components/file-upload', () => ({
  FileUpload: ({
    files = [],
    onFileDownload,
    onFileDownloadCancel,
    onFileRemove,
    downloadingFileIds,
    deletingFileIds,
    disabled,
    disabledTooltip,
    canRemove,
  }: {
    files?: UploadedFile[]
    onFileDownload?: (fileId: string, fileName: string) => void
    onFileDownloadCancel?: (fileId: string) => void
    onFileRemove?: (fileId: string) => void
    downloadingFileIds?: Set<string>
    deletingFileIds?: Set<string>
    disabled?: boolean
    disabledTooltip?: string
    canRemove?: boolean
  }) => (
    <div
      data-testid="file-upload"
      data-disabled={String(Boolean(disabled))}
      data-disabled-tooltip={disabledTooltip ?? ''}
      data-can-remove={String(Boolean(canRemove))}
    >
      {(files || []).map((f) => {
        const isDownloading = downloadingFileIds?.has(f.id) ?? false
        const isDeleting = deletingFileIds?.has(f.id) ?? false
        return (
          <div key={f.id} data-testid={`file-${f.id}`}>
            <span>{f.file.name}</span>
            <button
              type="button"
              data-testid={`download-${f.id}`}
              aria-busy={isDownloading}
              onClick={() => onFileDownload?.(f.id, f.file.name)}
            >
              Download
            </button>
            {isDownloading && (
              <button type="button" data-testid={`cancel-${f.id}`} onClick={() => onFileDownloadCancel?.(f.id)}>
                Cancel
              </button>
            )}
            <button
              type="button"
              data-testid={`remove-${f.id}`}
              aria-busy={isDeleting}
              disabled={isDeleting}
              onClick={() => onFileRemove?.(f.id)}
            >
              Remove
            </button>
          </div>
        )
      })}
    </div>
  ),
}))

describe('AIAgentFileUploadSection', () => {
  const showSuccess = vi.fn()
  const showError = vi.fn()

  const completedFile: UploadedFile = {
    id: 'file-1',
    file: new File(['content'], 'Report_Q2.pdf', { type: 'application/pdf' }),
    progress: 100,
    status: 'success',
  }

  const fileContext: FileContextType = {
    completedFiles: [completedFile],
    addFiles: vi.fn(),
    removeFile: vi.fn(),
    removeFilesByName: vi.fn(),
    isFilesError: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAlerts).mockReturnValue({
      showAlert: vi.fn(),
      showSuccess,
      showError,
      showWarning: vi.fn(),
      showInfo: vi.fn(),
      dismissAlert: vi.fn(),
      clearAllAlerts: vi.fn(),
    })
    vi.mocked(useFileStorageStatus).mockReturnValue({
      isConfigured: true,
      isLoading: false,
      isError: false,
      status: 'ok' as const,
    })
    vi.mocked(useFileUploadWithProgress).mockReturnValue({
      uploadFiles: vi.fn(),
      progress: [],
      error: null,
      uploading: false,
      cancelUpload: vi.fn(),
      reset: vi.fn(),
    })
  })

  function renderSection(overrides: Partial<Parameters<typeof AIAgentFileUploadSection>[0]> = {}) {
    return render(
      <AIAgentFileUploadSection
        projectId="project-1"
        isVersionView={false}
        hasExistingFiles
        fileContext={fileContext}
        {...overrides}
      />
    )
  }

  it('renders uploaded files and enables upload when storage is configured', () => {
    renderSection()

    expect(screen.getByTestId('file-upload')).toHaveAttribute('data-disabled', 'false')
    expect(screen.getByTestId('file-upload')).toHaveAttribute('data-can-remove', 'true')
    expect(screen.getByText('Report_Q2.pdf')).toBeInTheDocument()
  })

  it('disables upload in version view without a storage tooltip', () => {
    renderSection({ isVersionView: true })

    expect(screen.getByTestId('file-upload')).toHaveAttribute('data-disabled', 'true')
    expect(screen.getByTestId('file-upload')).toHaveAttribute('data-disabled-tooltip', '')
    expect(screen.getByTestId('file-upload')).toHaveAttribute('data-can-remove', 'false')
  })

  it('shows unconfigured storage tooltip when uploads are disabled', () => {
    vi.mocked(useFileStorageStatus).mockReturnValue({
      isConfigured: false,
      isLoading: false,
      isError: false,
      status: 'unconfigured' as const,
    })

    renderSection()

    expect(screen.getByTestId('file-upload')).toHaveAttribute('data-disabled', 'true')
    expect(screen.getByTestId('file-upload')).toHaveAttribute(
      'data-disabled-tooltip',
      FILE_STORAGE_UNCONFIGURED_MESSAGE
    )
  })

  it('shows unavailable storage tooltip when storage is errored', () => {
    vi.mocked(useFileStorageStatus).mockReturnValue({
      isConfigured: false,
      isLoading: false,
      isError: true,
      status: 'error' as const,
    })

    renderSection()

    expect(screen.getByTestId('file-upload')).toHaveAttribute('data-disabled-tooltip', FILE_STORAGE_UNAVAILABLE_MESSAGE)
  })

  it('downloads a file and shows a success toast', async () => {
    const user = userEvent.setup()
    vi.mocked(downloadFileById).mockResolvedValue('Report_Q2.pdf')

    renderSection()
    await user.click(screen.getByTestId('download-file-1'))

    await waitFor(() => {
      expect(downloadFileById).toHaveBeenCalledWith('file-1', 'Report_Q2.pdf', expect.any(AbortSignal))
    })
    await waitFor(() => {
      expect(showSuccess).toHaveBeenCalledWith({ title: 'Report_Q2.pdf downloaded successfully.' })
    })
    expect(showError).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByTestId('download-file-1')).toHaveAttribute('aria-busy', 'false')
    })
  })

  it('shows an error toast when download fails', async () => {
    const user = userEvent.setup()
    vi.mocked(downloadFileById).mockRejectedValue(new Error('network'))

    renderSection()
    await user.click(screen.getByTestId('download-file-1'))

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith({
        title: 'Unable to download Report_Q2.pdf. Please try again.',
      })
    })
    expect(showSuccess).not.toHaveBeenCalled()
  })

  it('does not toast when the download is aborted via Cancel', async () => {
    const user = userEvent.setup()
    let rejectDownload!: (error: unknown) => void
    vi.mocked(downloadFileById).mockImplementation((_id, _name, signal) => {
      return new Promise((_resolve, reject) => {
        rejectDownload = reject
        signal?.addEventListener('abort', () => {
          reject(new DOMException('The operation was aborted.', 'AbortError'))
        })
      })
    })

    renderSection()
    await user.click(screen.getByTestId('download-file-1'))

    expect(await screen.findByTestId('cancel-file-1')).toBeInTheDocument()
    await user.click(screen.getByTestId('cancel-file-1'))

    await waitFor(() => {
      expect(rejectDownload).toBeDefined()
    })
    await waitFor(() => {
      expect(screen.queryByTestId('cancel-file-1')).not.toBeInTheDocument()
    })
    expect(showSuccess).not.toHaveBeenCalled()
    expect(showError).not.toHaveBeenCalled()
  })

  it('does not toast on AbortError even when the signal is not marked aborted', async () => {
    const user = userEvent.setup()
    // Use a plain Error so we exercise the `error.name === 'AbortError'` branch
    // (DOMException may not be `instanceof Error` in jsdom).
    const abortError = new Error('The operation was aborted.')
    abortError.name = 'AbortError'
    vi.mocked(downloadFileById).mockRejectedValue(abortError)

    renderSection()
    await user.click(screen.getByTestId('download-file-1'))

    await waitFor(() => {
      expect(downloadFileById).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByTestId('download-file-1')).toHaveAttribute('aria-busy', 'false')
    })
    expect(showSuccess).not.toHaveBeenCalled()
    expect(showError).not.toHaveBeenCalled()
  })

  it('ignores a second download click while the first is in flight', async () => {
    const user = userEvent.setup()
    let resolveDownload!: (value: string) => void
    vi.mocked(downloadFileById).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDownload = resolve
        })
    )

    renderSection()
    await user.click(screen.getByTestId('download-file-1'))
    expect(await screen.findByTestId('cancel-file-1')).toBeInTheDocument()
    expect(screen.getByTestId('download-file-1')).toHaveAttribute('aria-busy', 'true')

    // Second click while in-flight should be a no-op (AbortController map guard).
    await user.click(screen.getByTestId('download-file-1'))
    expect(downloadFileById).toHaveBeenCalledTimes(1)

    resolveDownload('Report_Q2.pdf')
    await waitFor(() => {
      expect(showSuccess).toHaveBeenCalledTimes(1)
    })
  })

  it('tracks concurrent downloads independently in downloadingFileIds', async () => {
    const user = userEvent.setup()
    const resolvers = new Map<string, (value: string) => void>()
    vi.mocked(downloadFileById).mockImplementation((fileId) => {
      return new Promise((resolve) => {
        resolvers.set(fileId, resolve)
      })
    })

    const secondFile: UploadedFile = {
      id: 'file-2',
      file: new File(['notes'], 'Notes.txt', { type: 'text/plain' }),
      progress: 100,
      status: 'success',
    }

    renderSection({
      fileContext: {
        ...fileContext,
        completedFiles: [completedFile, secondFile],
      },
    })

    await user.click(screen.getByTestId('download-file-1'))
    await user.click(screen.getByTestId('download-file-2'))

    expect(await screen.findByTestId('cancel-file-1')).toBeInTheDocument()
    expect(screen.getByTestId('cancel-file-2')).toBeInTheDocument()
    expect(downloadFileById).toHaveBeenCalledTimes(2)

    resolvers.get('file-1')?.('Report_Q2.pdf')
    await waitFor(() => {
      expect(screen.queryByTestId('cancel-file-1')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('cancel-file-2')).toBeInTheDocument()

    resolvers.get('file-2')?.('Notes.txt')
    await waitFor(() => {
      expect(screen.queryByTestId('cancel-file-2')).not.toBeInTheDocument()
    })
    expect(showSuccess).toHaveBeenCalledTimes(2)
  })

  it('has no accessibility violations', async () => {
    const { container } = renderSection()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('detaches hydrated files on remove without calling the delete API', async () => {
    const user = userEvent.setup()
    const { deleteFileById } = await import('../../../utils/deleteFile')

    renderSection()
    await user.click(screen.getByTestId('remove-file-1'))

    expect(deleteFileById).not.toHaveBeenCalled()
    expect(fileContext.removeFile).toHaveBeenCalledWith('file-1')
  })
})
