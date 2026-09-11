import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, it, expect, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FileUpload } from './FileUpload'
import {
  computeUploadStatusProps,
  createDropRejectedHandler,
  formatAcceptedTypesForDisplay,
  type FileRejection,
  type UploadedFile,
} from './fileUploadUtils'

describe('computeUploadStatusProps', () => {
  const createFile = (name: string): File => new File(['x'], name, { type: 'image/png' })

  it('returns undefined toggle text when no files', () => {
    const result = computeUploadStatusProps([])
    expect(result.statusToggleText).toBeUndefined()
  })

  it('returns correct count text for mixed status files', () => {
    const files: UploadedFile[] = [
      { id: '1', file: createFile('a.png'), progress: 100, status: 'success' },
      { id: '2', file: createFile('b.png'), progress: 50, status: 'uploading' },
    ]
    const result = computeUploadStatusProps(files)
    expect(result.statusToggleText).toBe('1/2 files uploaded')
  })

  it('returns danger icon when any file has error', () => {
    const files: UploadedFile[] = [
      { id: '1', file: createFile('a.png'), progress: 100, status: 'success' },
      { id: '2', file: createFile('b.png'), progress: 30, status: 'error' },
    ]
    const result = computeUploadStatusProps(files)
    expect(result.statusToggleIcon).toBe('danger')
  })

  it('returns success icon and plural text when all files succeeded', () => {
    const files: UploadedFile[] = [
      { id: '1', file: createFile('a.png'), progress: 100, status: 'success' },
      { id: '2', file: createFile('b.png'), progress: 100, status: 'success' },
    ]
    const result = computeUploadStatusProps(files)
    expect(result.statusToggleIcon).toBe('success')
    expect(result.statusToggleText).toBe('2 files attached')
  })

  it('returns singular text when one file attached', () => {
    const files: UploadedFile[] = [{ id: '1', file: createFile('a.png'), progress: 100, status: 'success' }]
    const result = computeUploadStatusProps(files)
    expect(result.statusToggleIcon).toBe('success')
    expect(result.statusToggleText).toBe('1 file attached')
  })

  it('returns inProgress icon when upload in progress', () => {
    const files: UploadedFile[] = [
      { id: '1', file: createFile('a.png'), progress: 0, status: 'pending' },
      { id: '2', file: createFile('b.png'), progress: 50, status: 'uploading' },
    ]
    const result = computeUploadStatusProps(files)
    expect(result.statusToggleIcon).toBe('inProgress')
  })
})

describe('FileUpload', () => {
  function getFileInput(): HTMLInputElement {
    // eslint-disable-next-line testing-library/no-node-access -- PatternFly's MultipleFileUpload renders the file input as display:none; it has no accessible role or label by design since users interact via the "Upload" button, and userEvent.upload requires the input element directly
    return document.querySelector('input[type="file"]') as HTMLInputElement
  }

  describe('empty state', () => {
    it('renders dropzone with default text', () => {
      render(<FileUpload />)
      expect(screen.getByText('Drag and drop files here')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
    })

    it('renders custom title text', () => {
      render(<FileUpload titleText="Drop your files" />)
      expect(screen.getByText('Drop your files')).toBeInTheDocument()
    })

    it('renders custom browse button text', () => {
      render(<FileUpload browseButtonText="Choose Files" />)
      expect(screen.getByRole('button', { name: 'Choose Files' })).toBeInTheDocument()
    })

    it('displays accepted file types when provided', () => {
      render(<FileUpload acceptedMimeTypes={['.png', '.txt']} />)
      expect(screen.getByText('Accepted file types: PNG, TXT')).toBeInTheDocument()
    })

    it('displays custom info text over auto-generated', () => {
      render(<FileUpload acceptedMimeTypes={['.png']} infoText="Custom info" />)
      expect(screen.getByText('Custom info')).toBeInTheDocument()
      expect(screen.queryByText('Accepted file types: PNG')).not.toBeInTheDocument()
    })
  })

  describe('with files', () => {
    const createFile = (name: string, size = 1024): File => {
      return new File(['x'.repeat(size)], name, { type: 'image/png' })
    }

    const mockFiles: UploadedFile[] = [
      { id: '1', file: createFile('test1.png'), progress: 100, status: 'success' },
      { id: '2', file: createFile('test2.png'), progress: 50, status: 'uploading' },
    ]

    it('displays file count in status', () => {
      render(<FileUpload files={mockFiles} />)
      expect(screen.getByText('1/2 files uploaded')).toBeInTheDocument()
    })

    it('renders FileUploadItem for each file', () => {
      render(<FileUpload files={mockFiles} />)
      expect(screen.getByText('test1.png')).toBeInTheDocument()
      expect(screen.getByText('test2.png')).toBeInTheDocument()
    })

    it('shows success icon when all files complete', () => {
      const allSuccess: UploadedFile[] = [
        { id: '1', file: createFile('test1.png'), progress: 100, status: 'success' },
        { id: '2', file: createFile('test2.png'), progress: 100, status: 'success' },
      ]
      render(<FileUpload files={allSuccess} />)
      expect(screen.getByText('2 files attached')).toBeInTheDocument()
    })

    it('shows error icon when any file has error', () => {
      const withError: UploadedFile[] = [
        { id: '1', file: createFile('test1.png'), progress: 100, status: 'success' },
        { id: '2', file: createFile('test2.png'), progress: 30, status: 'error', errorMessage: 'Failed' },
      ]
      render(<FileUpload files={withError} />)
      expect(screen.getByText('1/2 files uploaded')).toBeInTheDocument()
    })
  })

  describe('callbacks', () => {
    it('calls onFileRemove when remove button is clicked', async () => {
      const user = userEvent.setup()
      const onFileRemove = vi.fn()
      const files: UploadedFile[] = [
        { id: 'file-1', file: new File([''], 'test.png'), progress: 100, status: 'success' },
      ]

      render(<FileUpload files={files} onFileRemove={onFileRemove} />)

      const removeButton = screen.getByLabelText('Remove test.png')
      await user.click(removeButton)

      expect(onFileRemove).toHaveBeenCalledWith('file-1')
    })

    it('calls onFileDownload when download button is clicked', async () => {
      const user = userEvent.setup()
      const onFileDownload = vi.fn()
      const files: UploadedFile[] = [
        { id: 'file-1', file: new File([''], 'Report_Q2.pdf'), progress: 100, status: 'success' },
      ]

      render(<FileUpload files={files} onFileDownload={onFileDownload} />)

      await user.click(screen.getByLabelText('Download Report_Q2.pdf'))

      expect(onFileDownload).toHaveBeenCalledWith('file-1', 'Report_Q2.pdf')
    })

    it('shows download spinner for each id in downloadingFileIds concurrently', () => {
      const files: UploadedFile[] = [
        { id: 'file-1', file: new File([''], 'Report_Q2.pdf'), progress: 100, status: 'success' },
        { id: 'file-2', file: new File([''], 'Notes.txt'), progress: 100, status: 'success' },
        { id: 'file-3', file: new File([''], 'Spec.md'), progress: 100, status: 'success' },
      ]

      render(<FileUpload files={files} onFileDownload={vi.fn()} downloadingFileIds={new Set(['file-1', 'file-3'])} />)

      expect(screen.getByLabelText('Download Report_Q2.pdf')).toHaveAttribute('disabled')
      expect(screen.getByLabelText('Download Notes.txt')).not.toHaveAttribute('disabled')
      expect(screen.getByLabelText('Download Spec.md')).toHaveAttribute('disabled')
    })

    it('shows remove spinner for each id in deletingFileIds and hides download', () => {
      const files: UploadedFile[] = [
        { id: 'file-1', file: new File([''], 'Report_Q2.pdf'), progress: 100, status: 'success' },
        { id: 'file-2', file: new File([''], 'Notes.txt'), progress: 100, status: 'success' },
      ]

      render(
        <FileUpload
          files={files}
          onFileDownload={vi.fn()}
          onFileRemove={vi.fn()}
          deletingFileIds={new Set(['file-1'])}
        />
      )

      expect(screen.getByLabelText('Remove Report_Q2.pdf')).toHaveAttribute('disabled')
      expect(screen.queryByLabelText('Download Report_Q2.pdf')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Remove Notes.txt')).not.toHaveAttribute('disabled')
      expect(screen.getByLabelText('Download Notes.txt')).toBeInTheDocument()
    })

    it('hides remove and shows Cancel for downloading files while others stay interactive', async () => {
      const user = userEvent.setup()
      const onFileDownloadCancel = vi.fn()
      const onFileRemove = vi.fn()
      const files: UploadedFile[] = [
        { id: 'file-1', file: new File([''], 'Report_Q2.pdf'), progress: 100, status: 'success' },
        { id: 'file-2', file: new File([''], 'Notes.txt'), progress: 100, status: 'success' },
      ]

      render(
        <FileUpload
          files={files}
          onFileDownload={vi.fn()}
          onFileDownloadCancel={onFileDownloadCancel}
          onFileRemove={onFileRemove}
          downloadingFileIds={new Set(['file-1'])}
        />
      )

      expect(screen.queryByLabelText('Remove Report_Q2.pdf')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Remove Notes.txt')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel download of Report_Q2.pdf' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Cancel download of Notes.txt' })).not.toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Cancel download of Report_Q2.pdf' }))
      expect(onFileDownloadCancel).toHaveBeenCalledWith('file-1')
    })

    it('calls onFilesSelected when files are dropped', async () => {
      const user = userEvent.setup()
      const onFilesSelected = vi.fn()
      render(<FileUpload onFilesSelected={onFilesSelected} />)

      const file = new File(['test content'], 'test.png', { type: 'image/png' })
      const input = getFileInput()

      await user.upload(input, file)

      expect(onFilesSelected).toHaveBeenCalledWith([file])
    })
  })

  describe('error handling', () => {
    it('clears error when file is removed', async () => {
      const user = userEvent.setup()
      const onFileRemove = vi.fn()
      const files: UploadedFile[] = [{ id: '1', file: new File([''], 'test.png'), progress: 100, status: 'success' }]

      render(<FileUpload files={files} onFileRemove={onFileRemove} />)

      const removeButton = screen.getByLabelText('Remove test.png')
      await user.click(removeButton)

      expect(onFileRemove).toHaveBeenCalled()
    })
  })

  describe('controlled vs uncontrolled', () => {
    it('uses internal state when files prop is not provided', () => {
      render(<FileUpload />)
      // Internal state starts empty
      expect(screen.queryByText(/files (uploaded|attached)/)).not.toBeInTheDocument()
    })

    it('uses controlled files when provided', () => {
      const files: UploadedFile[] = [{ id: '1', file: new File([''], 'test.png'), progress: 100, status: 'success' }]
      render(<FileUpload files={files} />)
      expect(screen.getByText('1 file attached')).toBeInTheDocument()
    })

    it('adds files to internal state when dropped in uncontrolled mode', async () => {
      const user = userEvent.setup()
      render(<FileUpload />)

      const file = new File(['test content'], 'dropped-file.png', { type: 'image/png' })
      const input = getFileInput()

      await user.upload(input, file)

      // File should appear in the UI
      expect(screen.getByText('dropped-file.png')).toBeInTheDocument()
      expect(screen.getByText('0/1 files uploaded')).toBeInTheDocument()
    })

    it('removes files from internal state in uncontrolled mode', async () => {
      const user = userEvent.setup()
      render(<FileUpload />)

      // First add a file
      const file = new File(['test content'], 'to-remove.png', { type: 'image/png' })
      const input = getFileInput()

      await user.upload(input, file)
      expect(screen.getByText('to-remove.png')).toBeInTheDocument()

      // Now remove it
      const removeButton = screen.getByLabelText('Remove to-remove.png')
      await user.click(removeButton)

      // File should be gone
      expect(screen.queryByText('to-remove.png')).not.toBeInTheDocument()
    })

    it('replaces file with same name when re-uploaded in uncontrolled mode', async () => {
      const user = userEvent.setup()
      render(<FileUpload />)

      const input = getFileInput()

      // Upload file first time
      const file1 = new File(['content1'], 'same-name.png', { type: 'image/png' })
      await user.upload(input, file1)
      expect(screen.getByText('same-name.png')).toBeInTheDocument()
      expect(screen.getByText('0/1 files uploaded')).toBeInTheDocument()

      // Upload file with same name again
      const file2 = new File(['content2'], 'same-name.png', { type: 'image/png' })
      await user.upload(input, file2)

      // Should still only have one file (replaced)
      expect(screen.getByText('same-name.png')).toBeInTheDocument()
      expect(screen.getByText('0/1 files uploaded')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has toggle aria label for file list', () => {
      const files: UploadedFile[] = [{ id: '1', file: new File([''], 'test.png'), progress: 100, status: 'success' }]
      render(<FileUpload files={files} />)
      expect(screen.getByLabelText('Toggle file list')).toBeInTheDocument()
    })

    it('has no accessibility violations when disabled with tooltip', async () => {
      const { container } = render(<FileUpload disabled disabledTooltip="S3 not configured" />)
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations while downloading with Cancel', async () => {
      const files: UploadedFile[] = [
        { id: 'file-1', file: new File([''], 'Report_Q2.pdf'), progress: 100, status: 'success' },
        { id: 'file-2', file: new File([''], 'Notes.txt'), progress: 100, status: 'success' },
      ]
      const { container } = render(
        <FileUpload
          files={files}
          onFileDownload={vi.fn()}
          onFileDownloadCancel={vi.fn()}
          onFileRemove={vi.fn()}
          downloadingFileIds={new Set(['file-1'])}
        />
      )

      expect(screen.getByRole('button', { name: 'Cancel download of Report_Q2.pdf' })).toBeInTheDocument()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('collapsed by default', () => {
    it('starts with file list collapsed when defaultStatusExpanded is false', () => {
      const files: UploadedFile[] = [{ id: '1', file: new File([''], 'test.png'), progress: 100, status: 'success' }]
      render(<FileUpload files={files} defaultStatusExpanded={false} />)
      expect(screen.getByText('1 file attached')).toBeInTheDocument()
      expect(screen.getByText('test.png')).not.toBeVisible()
    })

    it('expands file list when toggle is clicked', async () => {
      const user = userEvent.setup()
      const files: UploadedFile[] = [{ id: '1', file: new File([''], 'test.png'), progress: 100, status: 'success' }]
      render(<FileUpload files={files} defaultStatusExpanded={false} />)
      expect(screen.getByText('test.png')).not.toBeVisible()

      await user.click(screen.getByText('1 file attached'))

      expect(screen.getByText('test.png')).toBeVisible()
    })
  })

  describe('disabled state', () => {
    it('renders with disabled class when disabled', () => {
      const { container } = render(<FileUpload disabled />)
      // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access -- PatternFly MultipleFileUpload has no accessible role; checking CSS module class on the wrapper
      const wrapper = container.querySelector('.pf-v6-c-multiple-file-upload')
      expect(wrapper?.className).toMatch(/disabled/)
    })

    it('wraps content in tooltip when disabled with disabledTooltip', () => {
      render(<FileUpload disabled disabledTooltip="S3 not configured" />)
      expect(screen.getByText('Drag and drop files here')).toBeInTheDocument()
    })

    it('does not render tooltip when disabled without disabledTooltip', () => {
      render(<FileUpload disabled />)
      expect(screen.getByText('Drag and drop files here')).toBeInTheDocument()
    })

    it('does not render tooltip when not disabled', () => {
      render(<FileUpload disabledTooltip="S3 not configured" />)
      expect(screen.getByText('Drag and drop files here')).toBeInTheDocument()
    })
  })

  describe('accepted file types formatting', () => {
    it('formats MIME types with wildcard (e.g., image/*)', () => {
      render(<FileUpload acceptedMimeTypes={['image/*']} />)
      expect(screen.getByText('Accepted file types: image')).toBeInTheDocument()
    })

    it('formats full MIME types (e.g., application/pdf)', () => {
      render(<FileUpload acceptedMimeTypes={['application/pdf']} />)
      expect(screen.getByText('Accepted file types: PDF')).toBeInTheDocument()
    })

    it('formats multiple mixed types', () => {
      render(<FileUpload acceptedMimeTypes={['.png', 'image/*', 'application/pdf']} />)
      expect(screen.getByText('Accepted file types: PNG, image, PDF')).toBeInTheDocument()
    })

    it('displays no info text when no accepted types provided', () => {
      render(<FileUpload />)
      expect(screen.queryByText(/Accepted file types/)).not.toBeInTheDocument()
    })
  })

  describe('file rejection errors', () => {
    it('shows error when file exceeds size limit', async () => {
      const user = userEvent.setup()
      render(<FileUpload maxSizeBytes={10} />)

      const input = getFileInput()

      const largeFile = new File(['x'.repeat(100)], 'large-file.png', { type: 'image/png' })
      await user.upload(input, largeFile)

      expect(screen.getByText(/"large-file.png" exceeds.*limit/)).toBeInTheDocument()
    })

    it('shows error when file type is not accepted', () => {
      const setErrorMessage = vi.fn()
      const handler = createDropRejectedHandler({
        setErrorMessage,
        effectiveMaxSizeBytes: undefined,
        acceptedMimeTypes: ['image/png', '.yml'],
        maxFiles: undefined,
      })

      const rejections: FileRejection[] = [
        { file: new File([''], 'doc.txt'), errors: [{ code: 'file-invalid-type', message: 'Invalid type' }] },
      ]
      handler(rejections)

      expect(setErrorMessage).toHaveBeenCalledWith('Only PNG, YML files are allowed')
    })

    it('shows generic message for unknown rejection code', () => {
      const setErrorMessage = vi.fn()
      const handler = createDropRejectedHandler({
        setErrorMessage,
        effectiveMaxSizeBytes: undefined,
        acceptedMimeTypes: undefined,
        maxFiles: undefined,
      })

      const rejections: FileRejection[] = [
        { file: new File([''], 'file.bin'), errors: [{ code: 'unknown-error', message: 'Something went wrong' }] },
      ]
      handler(rejections)

      expect(setErrorMessage).toHaveBeenCalledWith('Something went wrong')
    })

    it('does nothing when rejections array is empty', () => {
      const setErrorMessage = vi.fn()
      const handler = createDropRejectedHandler({
        setErrorMessage,
        effectiveMaxSizeBytes: undefined,
        acceptedMimeTypes: undefined,
        maxFiles: undefined,
      })

      handler([])

      expect(setErrorMessage).not.toHaveBeenCalled()
    })

    it('shows error when too many files are uploaded', async () => {
      const user = userEvent.setup()
      render(<FileUpload maxFiles={1} />)

      const input = getFileInput()

      const file1 = new File(['a'], 'file1.png', { type: 'image/png' })
      const file2 = new File(['b'], 'file2.png', { type: 'image/png' })
      await user.upload(input, [file1, file2])

      expect(screen.getByText(/only 1 file allowed/i)).toBeInTheDocument()
    })

    it('clears rejection error when new valid files are dropped', async () => {
      const user = userEvent.setup()
      render(<FileUpload maxSizeBytes={10} />)

      const input = getFileInput()

      const largeFile = new File(['x'.repeat(100)], 'large.png', { type: 'image/png' })
      await user.upload(input, largeFile)
      expect(screen.getByText(/"large.png" exceeds.*limit/)).toBeInTheDocument()

      const smallFile = new File(['ok'], 'small.png', { type: 'image/png' })
      await user.upload(input, smallFile)
      expect(screen.queryByText(/"large.png" exceeds.*limit/)).not.toBeInTheDocument()
    })
  })

  describe('maxSizeMB prop', () => {
    it('uses maxSizeMB when provided', () => {
      // maxSizeMB is converted to bytes internally for dropzone
      render(<FileUpload maxSizeMB={5} />)
      expect(screen.getByText('Drag and drop files here')).toBeInTheDocument()
    })

    it('maxSizeBytes takes precedence when both provided', () => {
      render(<FileUpload maxSizeBytes={1024} maxSizeMB={5} />)
      expect(screen.getByText('Drag and drop files here')).toBeInTheDocument()
    })
  })

  describe('className prop', () => {
    it('applies custom className to container', () => {
      const { container } = render(<FileUpload className="custom-upload-class" />)

      // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
      expect(container.querySelector('.custom-upload-class')).toBeInTheDocument()
    })
  })

  describe('pending files', () => {
    it('shows 0 success count for all pending files', () => {
      const files: UploadedFile[] = [
        { id: '1', file: new File([''], 'test1.png'), progress: 0, status: 'pending' },
        { id: '2', file: new File([''], 'test2.png'), progress: 0, status: 'pending' },
      ]
      render(<FileUpload files={files} />)
      expect(screen.getByText('0/2 files uploaded')).toBeInTheDocument()
    })
  })
})

describe('formatAcceptedTypesForDisplay', () => {
  it('returns null for undefined or empty array', () => {
    expect(formatAcceptedTypesForDisplay(undefined)).toBeNull()
    expect(formatAcceptedTypesForDisplay([])).toBeNull()
  })

  it('formats file extensions', () => {
    expect(formatAcceptedTypesForDisplay(['.pdf', '.docx'])).toBe('PDF, DOCX')
  })

  it('formats wildcard mime types', () => {
    expect(formatAcceptedTypesForDisplay(['image/*', 'video/*'])).toBe('image, video')
  })

  it('formats specific mime types', () => {
    expect(formatAcceptedTypesForDisplay(['application/json'])).toBe('JSON')
  })

  it('handles mime types without subtype', () => {
    expect(formatAcceptedTypesForDisplay(['text/plain'])).toBe('PLAIN')
  })
})

describe('createDropRejectedHandler', () => {
  const setErrorMessage = vi.fn()

  beforeEach(() => {
    setErrorMessage.mockClear()
  })

  it('does nothing for empty rejections', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: undefined,
      acceptedMimeTypes: undefined,
      maxFiles: undefined,
    })
    handler([])
    expect(setErrorMessage).not.toHaveBeenCalled()
  })

  it('handles file-too-large error', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: 5 * 1024 * 1024,
      acceptedMimeTypes: undefined,
      maxFiles: undefined,
    })
    const rejection: FileRejection = {
      file: new File([''], 'big.pdf'),
      errors: [{ code: 'file-too-large', message: 'File is too large' }],
    }
    handler([rejection])
    expect(setErrorMessage).toHaveBeenCalledWith('"big.pdf" exceeds 5.0MB limit')
  })

  it('handles file-too-large without known max size', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: undefined,
      acceptedMimeTypes: undefined,
      maxFiles: undefined,
    })
    const rejection: FileRejection = {
      file: new File([''], 'big.pdf'),
      errors: [{ code: 'file-too-large', message: 'File is too large' }],
    }
    handler([rejection])
    expect(setErrorMessage).toHaveBeenCalledWith('"big.pdf" exceeds ?MB limit')
  })

  it('handles file-invalid-type error with accepted types', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: undefined,
      acceptedMimeTypes: ['.pdf', '.docx'],
      maxFiles: undefined,
    })
    const rejection: FileRejection = {
      file: new File([''], 'bad.exe'),
      errors: [{ code: 'file-invalid-type', message: 'Invalid type' }],
    }
    handler([rejection])
    expect(setErrorMessage).toHaveBeenCalledWith('Only PDF, DOCX files are allowed')
  })

  it('handles file-invalid-type error without accepted types', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: undefined,
      acceptedMimeTypes: undefined,
      maxFiles: undefined,
    })
    const rejection: FileRejection = {
      file: new File([''], 'bad.exe'),
      errors: [{ code: 'file-invalid-type', message: 'Invalid type' }],
    }
    handler([rejection])
    expect(setErrorMessage).toHaveBeenCalledWith('Only accepted types files are allowed')
  })

  it('handles too-many-files error with plural', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: undefined,
      acceptedMimeTypes: undefined,
      maxFiles: 3,
    })
    const rejection: FileRejection = {
      file: new File([''], 'extra.txt'),
      errors: [{ code: 'too-many-files', message: 'Too many' }],
    }
    handler([rejection])
    expect(setErrorMessage).toHaveBeenCalledWith('Only 3 files allowed')
  })

  it('handles too-many-files error with singular', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: undefined,
      acceptedMimeTypes: undefined,
      maxFiles: 1,
    })
    const rejection: FileRejection = {
      file: new File([''], 'extra.txt'),
      errors: [{ code: 'too-many-files', message: 'Too many' }],
    }
    handler([rejection])
    expect(setErrorMessage).toHaveBeenCalledWith('Only 1 file allowed')
  })

  it('handles unknown error codes with default message', () => {
    const handler = createDropRejectedHandler({
      setErrorMessage,
      effectiveMaxSizeBytes: undefined,
      acceptedMimeTypes: undefined,
      maxFiles: undefined,
    })
    const rejection: FileRejection = {
      file: new File([''], 'bad.txt'),
      errors: [{ code: 'unknown-error', message: 'Something went wrong' }],
    }
    handler([rejection])
    expect(setErrorMessage).toHaveBeenCalledWith('Something went wrong')
  })
})
