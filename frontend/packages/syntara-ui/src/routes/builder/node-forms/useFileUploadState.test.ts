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
  const uploadFiles = vi.fn()

  const hydratedFile: UploadedFile = {
    id: 'hydrated-file-1',
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

  function createFileContext(completedFiles: UploadedFile[] = [hydratedFile]): FileContextType {
    return {
      completedFiles,
      addFiles,
      removeFile,
      removeFilesByName,
      isFilesError: false,
    }
  }

  /** Upload a file in-session so its server id is tracked as deletable. */
  async function uploadSessionFile(
    result: { current: ReturnType<typeof useFileUploadState> },
    fileName = 'Report.pdf',
    serverId = 'session-file-1'
  ) {
    uploadFiles.mockResolvedValue({ files: [{ file_id: serverId }] })

    act(() => {
      result.current.handleFilesSelected([new File(['content'], fileName, { type: 'application/pdf' })])
    })

    await waitFor(() => {
      expect(addFiles).toHaveBeenCalled()
    })

    const uploaded = vi.mocked(addFiles).mock.calls.at(-1)?.[0] as UploadedFile[]
    expect(uploaded[0]?.id).toBe(serverId)
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
      uploadFiles,
      progress: [],
      error: null,
      uploading: false,
      cancelUpload: vi.fn(),
      reset: vi.fn(),
    })
    vi.mocked(deleteFileById).mockResolvedValue(undefined)
  })

  it('deletes a session-uploaded file from the server then removes it locally', async () => {
    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result)

    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    act(() => {
      result.current.handleFileRemove('session-file-1')
    })

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('session-file-1')
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-file-1')
    })
    expect(showSuccess).toHaveBeenCalledWith({ title: 'Report.pdf deleted successfully.' })
    expect(showError).not.toHaveBeenCalled()
  })

  it('detaches hydrated existing files locally without calling DELETE', () => {
    const { result } = renderHook(() => useFileUploadState(createFileContext([hydratedFile]), 'project-1'))

    act(() => {
      result.current.handleFileRemove('hydrated-file-1')
    })

    expect(deleteFileById).not.toHaveBeenCalled()
    expect(removeFile).toHaveBeenCalledWith('hydrated-file-1')
    expect(showSuccess).not.toHaveBeenCalled()
    expect(showError).not.toHaveBeenCalled()
  })

  it('after markPersisted, remove detaches locally without calling DELETE', async () => {
    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result)

    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    act(() => {
      result.current.markPersisted(['session-file-1'])
    })

    act(() => {
      result.current.handleFileRemove('session-file-1')
    })

    expect(deleteFileById).not.toHaveBeenCalled()
    expect(removeFile).toHaveBeenCalledWith('session-file-1')
    expect(showSuccess).not.toHaveBeenCalled()
  })

  it('session upload before persist still DELETEs on remove', async () => {
    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result)

    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    act(() => {
      result.current.handleFileRemove('session-file-1')
    })

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('session-file-1')
    })
  })

  it('keeps the session file and shows an error when server delete fails', async () => {
    vi.mocked(deleteFileById).mockRejectedValue(new Error('network'))
    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result)
    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    act(() => {
      result.current.handleFileRemove('session-file-1')
    })

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith({
        title: 'network',
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

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result)
    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    act(() => {
      result.current.handleFileRemove('session-file-1')
    })
    await waitFor(() => {
      expect(result.current.deletingFileIds.has('session-file-1')).toBe(true)
    })

    act(() => {
      result.current.handleFileRemove('session-file-1')
    })
    expect(deleteFileById).toHaveBeenCalledTimes(1)

    act(() => {
      resolveDelete()
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-file-1')
    })
  })

  it('ignores a synchronous double remove before deletingFileIds re-renders', async () => {
    let resolveDelete!: () => void
    vi.mocked(deleteFileById).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDelete = () => resolve()
        })
    )

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result)
    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    // Double-click in the same tick — state has not re-rendered yet.
    act(() => {
      result.current.handleFileRemove('session-file-1')
      result.current.handleFileRemove('session-file-1')
    })
    expect(deleteFileById).toHaveBeenCalledTimes(1)

    act(() => {
      resolveDelete()
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-file-1')
    })
  })

  it('on same-name re-upload, awaits DELETE for session upload then starts replacement', async () => {
    let resolveDelete!: () => void
    vi.mocked(deleteFileById).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDelete = () => resolve()
        })
    )

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result, 'Report.pdf', 'session-file-1')
    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile, hydratedFile]) })
    vi.mocked(deleteFileById).mockClear()
    vi.mocked(removeFilesByName).mockClear()
    vi.mocked(removeFile).mockClear()
    vi.mocked(uploadFiles).mockClear()
    uploadFiles.mockResolvedValue({ files: [{ file_id: 'session-file-2' }] })

    act(() => {
      result.current.handleFilesSelected([new File(['new'], 'Report.pdf', { type: 'application/pdf' })])
    })

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('session-file-1')
    })
    // UI / upload must not proceed until DELETE succeeds
    expect(removeFilesByName).not.toHaveBeenCalled()
    expect(uploadFiles).not.toHaveBeenCalled()

    act(() => {
      resolveDelete()
    })

    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-file-1')
    })
    await waitFor(() => {
      expect(removeFilesByName).toHaveBeenCalledWith(new Set(['Report.pdf']))
    })
    await waitFor(() => {
      expect(uploadFiles).toHaveBeenCalled()
    })
    expect(deleteFileById).not.toHaveBeenCalledWith('hydrated-file-1')
    expect(deleteFileById).toHaveBeenCalledTimes(1)
  })

  it('on same-name re-upload DELETE failure, keeps old chip and does not start replacement', async () => {
    vi.mocked(deleteFileById).mockRejectedValue(new Error('network'))

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result, 'Report.pdf', 'session-file-1')
    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })
    vi.mocked(deleteFileById).mockClear()
    vi.mocked(removeFilesByName).mockClear()
    vi.mocked(removeFile).mockClear()
    vi.mocked(uploadFiles).mockClear()
    vi.mocked(addFiles).mockClear()

    act(() => {
      result.current.handleFilesSelected([new File(['new'], 'Report.pdf', { type: 'application/pdf' })])
    })

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith({
        title: 'network',
      })
    })
    expect(removeFile).not.toHaveBeenCalled()
    expect(removeFilesByName).not.toHaveBeenCalled()
    expect(uploadFiles).not.toHaveBeenCalled()
    expect(addFiles).not.toHaveBeenCalled()
  })

  it('on same-name re-upload of a hydrated file only, detaches locally without DELETE', async () => {
    const { result } = renderHook(() => useFileUploadState(createFileContext([hydratedFile]), 'project-1'))
    uploadFiles.mockResolvedValue({ files: [{ file_id: 'session-file-2' }] })

    act(() => {
      result.current.handleFilesSelected([new File(['new'], 'Report.pdf', { type: 'application/pdf' })])
    })

    await waitFor(() => {
      expect(removeFilesByName).toHaveBeenCalledWith(new Set(['Report.pdf']))
    })
    expect(deleteFileById).not.toHaveBeenCalled()

    await waitFor(() => {
      expect(addFiles).toHaveBeenCalled()
    })
  })

  it('on same-name re-upload after markPersisted, detaches without DELETE', async () => {
    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result, 'Report.pdf', 'session-file-1')
    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    act(() => {
      result.current.markPersisted(['session-file-1'])
    })

    vi.mocked(deleteFileById).mockClear()
    vi.mocked(removeFilesByName).mockClear()
    uploadFiles.mockResolvedValue({ files: [{ file_id: 'session-file-2' }] })

    act(() => {
      result.current.handleFilesSelected([new File(['new'], 'Report.pdf', { type: 'application/pdf' })])
    })

    await waitFor(() => {
      expect(removeFilesByName).toHaveBeenCalledWith(new Set(['Report.pdf']))
    })
    expect(deleteFileById).not.toHaveBeenCalled()
  })

  it('multi-file replace defers UI clear until all session DELETEs succeed', async () => {
    const deleteResolvers: Array<() => void> = []
    vi.mocked(deleteFileById).mockImplementation(
      () =>
        new Promise((resolve) => {
          deleteResolvers.push(() => resolve())
        })
    )

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result, 'A.pdf', 'session-a')
    await uploadSessionFile(result, 'B.pdf', 'session-b')

    const sessionA: UploadedFile = {
      id: 'session-a',
      file: new File(['a'], 'A.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    const sessionB: UploadedFile = {
      id: 'session-b',
      file: new File(['b'], 'B.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionA, sessionB]) })
    vi.mocked(deleteFileById).mockClear()
    vi.mocked(removeFile).mockClear()
    vi.mocked(removeFilesByName).mockClear()
    vi.mocked(uploadFiles).mockClear()
    uploadFiles.mockResolvedValue({
      files: [{ file_id: 'session-a-2' }, { file_id: 'session-b-2' }],
    })

    act(() => {
      result.current.handleFilesSelected([
        new File(['a2'], 'A.pdf', { type: 'application/pdf' }),
        new File(['b2'], 'B.pdf', { type: 'application/pdf' }),
      ])
    })

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('session-a')
    })
    // First DELETE in flight — UI must not clear yet
    expect(removeFile).not.toHaveBeenCalled()
    expect(removeFilesByName).not.toHaveBeenCalled()
    expect(uploadFiles).not.toHaveBeenCalled()

    act(() => {
      deleteResolvers[0]?.()
    })

    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('session-b')
    })
    // Second DELETE in flight — still no UI clear (batch gate)
    expect(removeFile).not.toHaveBeenCalled()
    expect(uploadFiles).not.toHaveBeenCalled()

    act(() => {
      deleteResolvers[1]?.()
    })

    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-a')
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-b')
    })
    await waitFor(() => {
      expect(uploadFiles).toHaveBeenCalled()
    })
  })

  it('multi-file replace stops on first DELETE failure and only clears prior successes', async () => {
    vi.mocked(deleteFileById).mockImplementation((fileId: string) => {
      if (fileId === 'session-b') {
        return Promise.reject(new Error('network'))
      }
      return Promise.resolve()
    })

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result, 'A.pdf', 'session-a')
    await uploadSessionFile(result, 'B.pdf', 'session-b')

    const sessionA: UploadedFile = {
      id: 'session-a',
      file: new File(['a'], 'A.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    const sessionB: UploadedFile = {
      id: 'session-b',
      file: new File(['b'], 'B.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionA, sessionB]) })
    vi.mocked(deleteFileById).mockClear()
    vi.mocked(removeFile).mockClear()
    vi.mocked(removeFilesByName).mockClear()
    vi.mocked(uploadFiles).mockClear()
    vi.mocked(addFiles).mockClear()

    act(() => {
      result.current.handleFilesSelected([
        new File(['a2'], 'A.pdf', { type: 'application/pdf' }),
        new File(['b2'], 'B.pdf', { type: 'application/pdf' }),
      ])
    })

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith({
        title: 'network',
      })
    })
    // A was deleted on the server — clear its chip so it is not a zombie. Keep B.
    expect(removeFile).toHaveBeenCalledWith('session-a')
    expect(removeFile).not.toHaveBeenCalledWith('session-b')
    expect(removeFilesByName).not.toHaveBeenCalled()
    expect(uploadFiles).not.toHaveBeenCalled()
    expect(addFiles).not.toHaveBeenCalled()
  })

  it('aborts replace when a matching session file delete is already in flight', async () => {
    let resolveDelete!: () => void
    vi.mocked(deleteFileById).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDelete = () => resolve()
        })
    )

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result, 'Report.pdf', 'session-file-1')
    const sessionFile: UploadedFile = {
      id: 'session-file-1',
      file: new File(['content'], 'Report.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionFile]) })

    act(() => {
      result.current.handleFileRemove('session-file-1')
    })
    await waitFor(() => {
      expect(result.current.deletingFileIds.has('session-file-1')).toBe(true)
    })

    vi.mocked(deleteFileById).mockClear()
    vi.mocked(uploadFiles).mockClear()
    vi.mocked(removeFilesByName).mockClear()

    act(() => {
      result.current.handleFilesSelected([new File(['new'], 'Report.pdf', { type: 'application/pdf' })])
    })

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith({
        title: 'A file delete is already in progress. Please try again.',
      })
    })
    expect(deleteFileById).not.toHaveBeenCalled()
    expect(uploadFiles).not.toHaveBeenCalled()
    expect(removeFilesByName).not.toHaveBeenCalled()

    act(() => {
      resolveDelete()
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-file-1')
    })
  })

  it('multi-file replace marks all batch chips as deleting up front', async () => {
    const deleteResolvers: Array<() => void> = []
    vi.mocked(deleteFileById).mockImplementation(
      () =>
        new Promise((resolve) => {
          deleteResolvers.push(() => resolve())
        })
    )

    const { result, rerender } = renderHook(({ ctx }) => useFileUploadState(ctx, 'project-1'), {
      initialProps: { ctx: createFileContext([]) },
    })

    await uploadSessionFile(result, 'A.pdf', 'session-a')
    await uploadSessionFile(result, 'B.pdf', 'session-b')

    const sessionA: UploadedFile = {
      id: 'session-a',
      file: new File(['a'], 'A.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    const sessionB: UploadedFile = {
      id: 'session-b',
      file: new File(['b'], 'B.pdf', { type: 'application/pdf' }),
      progress: 100,
      status: 'success',
    }
    rerender({ ctx: createFileContext([sessionA, sessionB]) })

    act(() => {
      result.current.handleFilesSelected([
        new File(['a2'], 'A.pdf', { type: 'application/pdf' }),
        new File(['b2'], 'B.pdf', { type: 'application/pdf' }),
      ])
    })

    await waitFor(() => {
      expect(result.current.deletingFileIds.has('session-a')).toBe(true)
      expect(result.current.deletingFileIds.has('session-b')).toBe(true)
    })

    act(() => {
      deleteResolvers[0]?.()
    })
    await waitFor(() => {
      expect(deleteFileById).toHaveBeenCalledWith('session-b')
    })
    expect(result.current.deletingFileIds.has('session-b')).toBe(true)

    uploadFiles.mockResolvedValue({
      files: [{ file_id: 'session-a-2' }, { file_id: 'session-b-2' }],
    })
    act(() => {
      deleteResolvers[1]?.()
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-a')
    })
    await waitFor(() => {
      expect(removeFile).toHaveBeenCalledWith('session-b')
    })
  })
})
