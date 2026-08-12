import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useFileUploadWithProgress } from '../../../hooks/useFileUploadWithProgress'
import { useAlerts } from '../../../providers/alerts'
import { deleteFileById } from '../../../utils/deleteFile'
import type { UploadedFile } from '../components/file-upload'

import { useFileUploadState, type FileContextType } from './useFileUploadState'

vi.mock('../../../hooks/useFileUploadWithProgress', () => ({
  useFileUploadWithProgress: vi.fn(),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(),
}))

vi.mock('../../../utils/deleteFile', () => ({
  deleteFileById: vi.fn(),
}))

vi.mock('../../../utils/generateUUID', () => ({
  generateUUID: () => 'local-uuid',
}))

describe('useFileUploadState', () => {
  const showSuccess = vi.fn()
  const showError = vi.fn()
  const removeFile = vi.fn()
  const removeFilesByName = vi.fn()
  const addFiles = vi.fn()

  const successFile: UploadedFile = {
    id: 'server-file-1',
    file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
    progress: 100,
    status: 'success',
  }

  const errorFile: UploadedFile = {
    id: 'local-error-1',
    file: new File(['bad'], 'Broken.txt', { type: 'text/plain' }),
    progress: 0,
    status: 'error',
    errorMessage: 'Upload failed. Please try again.',
  }

  function createFileContext(completedFiles: UploadedFile[] = [successFile]): FileContextType {
    return {
      completedFiles,
      addFiles,
      removeFile,
      removeFilesByName,
      isFilesError: false,
    }
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
    vi.mocked(useFileUploadWithProgress).mockReturnValue({
      uploadFiles: vi.fn(),
      progress: [],
      error: null,
      uploading: false,
      cancelUpload: vi.fn(),
      reset: vi.fn(),
    })
    vi.mocked(deleteFileById).mockResolvedValue(undefined)
  })

  it('deletes a successfully uploaded file from the server then removes it locally', async () => {
    const { result } = renderHook(() => useFileUploadState(createFileContext(), 'project-1'))

    act(() => {
      result.current.handleFileRemove('server-file-1')
    })

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('server-file-1')
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('server-file-1')
    })
    expect(showSuccess).toHaveBeenCalledWith({ title: 'Report.pdf deleted successfully.' })
    expect(showError).not.toHaveBeenCalled()
  })

  it('keeps the file and shows an error when server delete fails', async () => {
    vi.mocked(deleteFileById).mockRejectedValue(new Error('network'))
    const { result } = renderHook(() => useFileUploadState(createFileContext(), 'project-1'))

    act(() => {
      result.current.handleFileRemove('server-file-1')
    })

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith({
        title: 'Unable to delete Report.pdf. Please try again.',
      })
    })
    expect(removeFile).not.toHaveBeenCalled()
    expect(showSuccess).not.toHaveBeenCalled()
  })

  it('removes failed uploads locally without calling the delete API', () => {
    const { result } = renderHook(() => useFileUploadState(createFileContext([errorFile]), 'project-1'))

    act(() => {
      result.current.handleFileRemove('local-error-1')
    })

    expect(deleteFileById).not.toHaveBeenCalled()
    expect(removeFile).toHaveBeenCalledWith('local-error-1')
    expect(showSuccess).not.toHaveBeenCalled()
    expect(showError).not.toHaveBeenCalled()
  })

  it('ignores a second remove click while delete is in flight', async () => {
    let resolveDelete!: () => void
    vi.mocked(deleteFileById).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDelete = () => resolve()
        })
    )

    const { result } = renderHook(() => useFileUploadState(createFileContext(), 'project-1'))

    act(() => {
      result.current.handleFileRemove('server-file-1')
    })
    await waitFor(() => {
      expect(result.current.deletingFileIds.has('server-file-1')).toBe(true)
    })

    act(() => {
      result.current.handleFileRemove('server-file-1')
    })
    expect(deleteFileById).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveDelete()
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('server-file-1')
    })
  })
})
