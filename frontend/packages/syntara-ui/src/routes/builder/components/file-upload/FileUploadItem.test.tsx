import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { FileUploadItem } from './FileUploadItem'

describe('FileUploadItem', () => {
  const createFile = (name: string, size = 1024): File => {
    return new File(['x'.repeat(size)], name, { type: 'image/png' })
  }

  describe('file info display', () => {
    it('renders file name', () => {
      const file = createFile('document.png')
      render(<FileUploadItem file={file} fileId="1" />)
      expect(screen.getByText('document.png')).toBeInTheDocument()
    })

    it('renders long file names with middle Truncate', () => {
      const longName = 'very-long-context-filename-that-should-truncate-in-the-middle.pdf'
      const file = createFile(longName)
      render(<FileUploadItem file={file} fileId="1" />)
      // PatternFly middle Truncate splits across start/end segments; assert via combined textContent.
      expect(
        screen.getByText(
          (_content, element) =>
            element?.classList.contains('pf-v6-c-truncate') === true && element.textContent === longName
        )
      ).toBeInTheDocument()
      expect(screen.getByText(/\.pdf$/)).toBeInTheDocument()
    })

    it('renders custom file name when provided', () => {
      const file = createFile('original.png')
      render(<FileUploadItem file={file} fileId="1" fileName="renamed.png" />)
      expect(screen.getByText('renamed.png')).toBeInTheDocument()
      expect(screen.queryByText('original.png')).not.toBeInTheDocument()
    })

    it('renders file extension', () => {
      const file = createFile('document.pdf', 2048)
      render(<FileUploadItem file={file} fileId="1" />)
      expect(screen.getByText(/PDF/)).toBeInTheDocument()
    })

    it('renders file size in bytes', () => {
      const file = createFile('small.png', 500)
      render(<FileUploadItem file={file} fileId="1" />)
      expect(screen.getByText(/500 B/)).toBeInTheDocument()
    })

    it('renders file size in KB', () => {
      const file = createFile('medium.png', 2048)
      render(<FileUploadItem file={file} fileId="1" />)
      expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument()
    })

    it('renders file size in MB', () => {
      const file = createFile('large.png', 2 * 1024 * 1024)
      render(<FileUploadItem file={file} fileId="1" />)
      expect(screen.getByText(/2\.0 MB/)).toBeInTheDocument()
    })
  })

  describe('status display', () => {
    it('does not show progress bar for pending status', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" status="pending" progress={0} />)
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    })

    it('shows progress bar for uploading status', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" status="uploading" progress={50} />)
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('shows progress bar for success status', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" status="success" progress={100} />)
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('shows progress bar for error status', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" status="error" progress={30} />)
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('displays error message when provided', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" status="error" progress={30} errorMessage="Upload failed" />)
      expect(screen.getByText(/Upload failed/)).toBeInTheDocument()
    })
  })

  describe('remove button', () => {
    it('renders remove button', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" onRemove={() => {}} />)
      expect(screen.getByLabelText('Remove file')).toBeInTheDocument()
    })

    it('does not render remove button when onRemove is omitted', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" />)
      expect(screen.queryByLabelText('Remove file')).not.toBeInTheDocument()
    })

    it('calls onRemove when clicked', async () => {
      const user = userEvent.setup()
      const onRemove = vi.fn()
      const file = createFile('test.png')

      render(<FileUploadItem file={file} fileId="1" onRemove={onRemove} />)

      await user.click(screen.getByLabelText('Remove file'))
      expect(onRemove).toHaveBeenCalledTimes(1)
    })

    it('uses custom aria-label when provided', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" onRemove={() => {}} removeButtonAriaLabel="Delete test.png" />)
      expect(screen.getByLabelText('Delete test.png')).toBeInTheDocument()
    })
  })

  describe('download button', () => {
    it('renders download button to the left of remove for successful uploads', () => {
      const file = createFile('Report_Q2.pdf')
      render(
        <FileUploadItem
          file={file}
          fileId="1"
          status="success"
          onDownload={() => {}}
          onRemove={() => {}}
          downloadButtonAriaLabel="Download Report_Q2.pdf"
        />
      )

      const allButtons = screen.getAllByRole('button')
      const downloadIndex = allButtons.findIndex((b) => b.getAttribute('aria-label') === 'Download Report_Q2.pdf')
      const removeIndex = allButtons.findIndex((b) => b.getAttribute('aria-label') === 'Remove file')
      expect(downloadIndex).toBeLessThan(removeIndex)
    })

    it('does not render download button when status is not success', () => {
      const file = createFile('Report_Q2.pdf')
      render(<FileUploadItem file={file} fileId="1" status="uploading" onDownload={() => {}} />)
      expect(screen.queryByLabelText('Download file')).not.toBeInTheDocument()
    })

    it('calls onDownload when clicked', async () => {
      const user = userEvent.setup()
      const onDownload = vi.fn()
      const file = createFile('Report_Q2.pdf')

      render(<FileUploadItem file={file} fileId="1" status="success" onDownload={onDownload} />)

      await user.click(screen.getByLabelText('Download file'))
      expect(onDownload).toHaveBeenCalledTimes(1)
    })

    it('shows loading state while downloading', () => {
      const file = createFile('Report_Q2.pdf')
      render(<FileUploadItem file={file} fileId="1" status="success" onDownload={() => {}} isDownloading />)
      expect(screen.getByLabelText('Download file')).toHaveAttribute('disabled')
    })

    it('hides remove button while downloading', () => {
      const file = createFile('Report_Q2.pdf')
      render(
        <FileUploadItem
          file={file}
          fileId="1"
          status="success"
          onDownload={() => {}}
          onRemove={() => {}}
          isDownloading
        />
      )
      expect(screen.queryByLabelText('Remove file')).not.toBeInTheDocument()
    })

    it('shows loading state on remove while deleting and hides download', () => {
      const file = createFile('Report_Q2.pdf')
      render(
        <FileUploadItem file={file} fileId="1" status="success" onDownload={() => {}} onRemove={() => {}} isDeleting />
      )
      expect(screen.getByLabelText('Remove file')).toHaveAttribute('disabled')
      expect(screen.queryByLabelText('Download file')).not.toBeInTheDocument()
    })

    it('shows Cancel link while downloading and calls onCancelDownload', async () => {
      const user = userEvent.setup()
      const onCancelDownload = vi.fn()
      const file = createFile('Report_Q2.pdf')

      render(
        <FileUploadItem
          file={file}
          fileId="1"
          status="success"
          onDownload={() => {}}
          onCancelDownload={onCancelDownload}
          isDownloading
          cancelDownloadAriaLabel="Cancel download of Report_Q2.pdf"
        />
      )

      const cancel = screen.getByRole('button', { name: 'Cancel download of Report_Q2.pdf' })
      expect(cancel).toHaveTextContent('Cancel')
      await user.click(cancel)
      expect(onCancelDownload).toHaveBeenCalledTimes(1)
    })

    it('does not show Cancel link when not downloading', () => {
      const file = createFile('Report_Q2.pdf')
      render(
        <FileUploadItem file={file} fileId="1" status="success" onDownload={() => {}} onCancelDownload={() => {}} />
      )
      expect(screen.queryByRole('button', { name: 'Cancel download' })).not.toBeInTheDocument()
    })

    it('does not show Cancel when downloading without onCancelDownload', () => {
      const file = createFile('Report_Q2.pdf')
      render(<FileUploadItem file={file} fileId="1" status="success" onDownload={() => {}} isDownloading />)
      expect(screen.queryByRole('button', { name: 'Cancel download' })).not.toBeInTheDocument()
      expect(screen.getByLabelText('Download file')).toHaveAttribute('disabled')
    })

    it('uses provided fileSize over the File object size', () => {
      const file = createFile('Report_Q2.pdf', 10)
      render(<FileUploadItem file={file} fileId="1" fileSize={2048} />)
      expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has accessible progress bar with file name', () => {
      const file = createFile('document.png')
      render(<FileUploadItem file={file} fileId="1" status="uploading" progress={50} />)
      expect(screen.getByLabelText('document.png upload progress')).toBeInTheDocument()
    })

    it('has no accessibility violations with middle Truncate filename', async () => {
      const longName = 'very-long-context-filename-that-should-truncate-in-the-middle.pdf'
      const file = createFile(longName)
      const { container } = render(
        <FileUploadItem
          file={file}
          fileId="1"
          status="success"
          onDownload={() => {}}
          onRemove={() => {}}
          downloadButtonAriaLabel={`Download ${longName}`}
          removeButtonAriaLabel={`Remove ${longName}`}
        />
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations while downloading with Cancel', async () => {
      const file = createFile('Report_Q2.pdf')
      const { container } = render(
        <FileUploadItem
          file={file}
          fileId="1"
          status="success"
          onDownload={() => {}}
          onCancelDownload={() => {}}
          onRemove={() => {}}
          isDownloading
          downloadButtonAriaLabel="Download Report_Q2.pdf"
          cancelDownloadAriaLabel="Cancel download of Report_Q2.pdf"
          removeButtonAriaLabel="Remove Report_Q2.pdf"
        />
      )

      expect(screen.getByRole('button', { name: 'Cancel download of Report_Q2.pdf' })).toBeInTheDocument()
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })

  describe('styling', () => {
    it('applies custom className', () => {
      const file = createFile('test.png')
      const { container } = render(<FileUploadItem file={file} fileId="1" className="custom-class" />)

      // eslint-disable-next-line testing-library/no-node-access
      expect(container.firstChild).toHaveClass('custom-class')
    })
  })

  describe('edge cases', () => {
    it('handles file without extension', () => {
      const file = new File(['content'], 'README', { type: 'text/plain' })
      render(<FileUploadItem file={file} fileId="1" />)
      // File name appears as both display name and extension (getFileExtension returns the whole name)
      expect(screen.getAllByText('README').length).toBeGreaterThanOrEqual(1)
      // Should show the file size
      expect(screen.getByText(/7 B/)).toBeInTheDocument()
    })

    it('does not show progress bar when progress is undefined', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" status="uploading" />)
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    })

    it('uses default pending status when not provided', () => {
      const file = createFile('test.png')
      render(<FileUploadItem file={file} fileId="1" progress={50} />)
      // pending status doesn't show progress bar
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    })
  })
})
